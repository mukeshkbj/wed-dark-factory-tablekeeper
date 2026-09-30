#!/usr/bin/env python3
"""Spec-derived checks for the stage-1 service, stdlib only.

Runs against a live server: BASE_URL env or http://localhost:8080.
These are independent checks authored from the specification; they do not
reuse the shipped test suite.

Usage:
    python tests/local_checks.py            # BASE_URL=http://localhost:8080
    BASE_URL=http://localhost:9000 python tests/local_checks.py
"""
from __future__ import annotations

import datetime as dt
import http.client
import json
import os
import re
import sys
import threading
import urllib.parse
import uuid

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
_parsed = urllib.parse.urlsplit(BASE_URL)
_HOST = _parsed.hostname or "localhost"
_PORT = _parsed.port or (443 if _parsed.scheme == "https" else 80)

REFERENCE_RE = re.compile(r"^[A-Z0-9]{6,12}$")
OFFSET_RE = re.compile(r"([+-]\d{2}:\d{2}|Z)$")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_failures = []
_checks = 0


def check(name):
    def deco(fn):
        global _checks
        _checks += 1
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report and continue
            _failures.append(name)
            print(f"FAIL {name}: {exc}")
        else:
            print(f"PASS {name}")
    return deco


def req(method, path, body=None, token=None, key=None, params=None,
        raw_body=None, headers=None):
    if params:
        path = path + "?" + urllib.parse.urlencode(params)
    payload = raw_body
    if payload is None and body is not None:
        payload = json.dumps(body)
    conn = http.client.HTTPConnection(_HOST, _PORT, timeout=15)
    hdrs = {"Content-Type": "application/json"}
    if token is not None:
        hdrs["Authorization"] = f"Bearer {token}"
    if key is not None:
        hdrs["Idempotency-Key"] = key
    if headers:
        hdrs.update(headers)
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    status = resp.status
    conn.close()
    out = None
    if data:
        try:
            out = json.loads(data)
        except ValueError:
            out = data
    if status >= 500:
        raise AssertionError(f"{method} {path} -> {status} (5xx forbidden): {out!r}")
    return status, out


def want(cond, msg):
    if not cond:
        raise AssertionError(msg)


def expect(resp, status):
    got, body = resp
    want(got == status, f"expected {status}, got {got}: {body!r}")
    return body


def expect_error(resp, status, code):
    body = expect(resp, status)
    want(isinstance(body, dict) and body.get("error", {}).get("code") == code,
         f"expected error {code}, got {body!r}")
    return body


def new_key():
    return uuid.uuid4().hex


# ---------------------------------------------------------------- fixtures

def all_week(opens="18:00", closes="23:00"):
    return [{"weekday": d, "opens": opens, "closes": closes} for d in WEEKDAYS]


def restaurant(rid="r_anker", **kw):
    base = {
        "id": rid,
        "name": "Zum Anker",
        "timezone": "Europe/Berlin",
        "slot_minutes": 30,
        "reservation_duration_minutes": 90,
        "cancellation_cutoff_minutes": 120,
        "opening_hours": all_week(),
        "tables": [
            {"id": "t_1", "label": "1", "capacity": 2},
            {"id": "t_2", "label": "2", "capacity": 4},
            {"id": "t_3", "label": "3", "capacity": 6},
        ],
    }
    base.update(kw)
    return base


def fixture(**kw):
    return {
        "users": kw.get("users", [
            {"id": "u_ada", "email": "ada@example.com",
             "password": "correct horse", "display_name": "Ada"},
            {"id": "u_bob", "email": "bob@example.com",
             "password": "correct horse", "display_name": "Bob"},
        ]),
        "restaurants": kw.get("restaurants", [restaurant()]),
        "reservations": kw.get("reservations", []),
    }


def reset(fx=None):
    return req("POST", "/_test/reset", body=fx if fx is not None else fixture())


def login(email="ada@example.com", password="correct horse"):
    status, body = req("POST", "/auth/login",
                       body={"email": email, "password": password})
    assert status == 200, f"login failed: {status} {body}"
    return body["token"]


def book_date(days=7):
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def local(date, hhmm="19:00"):
    return f"{date}T{hhmm}"


def book(token, date=None, at="19:00", table_id="t_2", party_size=4, key=None,
         restaurant_id="r_anker"):
    return req("POST", "/reservations", body={
        "restaurant_id": restaurant_id, "table_id": table_id,
        "starts_at_local": local(date or book_date(), at),
        "party_size": party_size,
    }, token=token, key=key or new_key())


def expected_slots(opens="18:00", closes="23:00", slot=30, dur=90):
    def mins(s):
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    out, t, end = [], mins(opens), mins(closes)
    while t + dur <= end:
        out.append(f"{t // 60:02d}:{t % 60:02d}")
        t += slot
    return out


# ------------------------------------------------------------------- checks

@check("health returns ok")
def _():
    body = expect(req("GET", "/health"), 200)
    want(body == {"status": "ok"}, f"unexpected health body {body!r}")


@check("reset seeds and reseeds")
def _():
    expect(reset(), 204)
    expect(reset(fixture(restaurants=[restaurant(name="Renamed")])), 204)
    body = expect(req("GET", "/restaurants"), 200)
    want(body["restaurants"][0]["name"] == "Renamed", "reseed did not apply")
    expect(reset(), 204)


@check("reset validates structure")
def _():
    expect_error(req("POST", "/_test/reset", raw_body="{nope"), 400,
                 "malformed_request")
    expect_error(reset({"users": "x"}), 400, "malformed_request")
    expect_error(reset(fixture(users=[{"id": "u" * 65, "email": "a@b.c",
                                      "password": "long enough",
                                      "display_name": "X"}])), 422,
                 "validation_failed")
    expect_error(reset(fixture(
        reservations=[{"id": "r1", "reference": "R" * 65, "user_id": "u_ada",
                       "restaurant_id": "r_anker", "table_id": "t_2",
                       "starts_at_local": local(book_date()), "party_size": 2}])),
        422, "validation_failed")
    expect(reset(), 204)


@check("signup, login and auth errors")
def _():
    expect(reset(), 204)
    status, body = req("POST", "/auth/signup", body={
        "email": "carol@example.com", "password": "long enough",
        "display_name": "Carol"})
    want(status == 201, f"signup -> {status}")
    want(set(body) >= {"user_id", "display_name", "token"},
         f"signup body {body!r}")
    expect_error(req("POST", "/auth/signup", body={
        "email": "ada@example.com", "password": "correct horse",
        "display_name": "A"}), 409, "email_taken")
    expect_error(req("POST", "/auth/signup", body={
        "email": "d@example.com", "password": "short",
        "display_name": "D"}), 422, "validation_failed")
    expect_error(req("POST", "/auth/signup", body={
        "email": "not-an-email", "password": "correct horse",
        "display_name": "E"}), 422, "validation_failed")
    expect_error(req("POST", "/auth/signup", body={
        "email": 17, "password": "correct horse",
        "display_name": "F"}), 400, "malformed_request")
    expect_error(req("POST", "/auth/login", body={
        "email": "ada@example.com", "password": "wrong password"}),
        401, "unauthenticated")
    expect_error(req("POST", "/auth/login", body={
        "email": "nobody@example.com", "password": "correct horse"}),
        401, "unauthenticated")
    expect(req("GET", "/reservations"), 401)
    expect(req("GET", "/reservations", token="nope"), 401)
    # Both seeded passwords work immediately.
    login("ada@example.com", "correct horse")
    login("bob@example.com", "correct horse")


@check("restaurants list and detail are public")
def _():
    expect(reset(), 204)
    body = expect(req("GET", "/restaurants"), 200)
    want(body["restaurants"][0]["id"] == "r_anker", "list shape")
    detail = expect(req("GET", "/restaurants/r_anker"), 200)
    for f in ("slot_minutes", "reservation_duration_minutes",
              "cancellation_cutoff_minutes", "opening_hours", "tables"):
        want(f in detail, f"detail missing {f}")
    expect_error(req("GET", "/restaurants/r_nope"), 404, "not_found")


@check("availability grid math")
def _():
    expect(reset(), 204)
    date = book_date()
    status, body = req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 2})
    want(status == 200, f"availability -> {status}")
    want(body["restaurant_id"] == "r_anker" and body["date"] == date
         and body["timezone"] == "Europe/Berlin", f"envelope {body!r}")
    got = [s["starts_at_local"].split("T")[1] for s in body["slots"]]
    want(got == expected_slots(), f"slots {got}")
    first = body["slots"][0]
    want(first["starts_at_local"] == local(date, "18:00")
         and first["starts_at"].startswith(f"{date}T18:00:00")
         and OFFSET_RE.search(first["starts_at"]), f"slot shape {first!r}")
    want(first["available_table_ids"] == ["t_1", "t_2", "t_3"],
         f"fixture order {first!r}")
    # Capacity filter: party of 5 leaves only t_3.
    big = expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 5}), 200)
    want(big["slots"][0]["available_table_ids"] == ["t_3"], "capacity filter")
    # Parameter validation.
    for drop in ("restaurant_id", "date", "party_size"):
        params = {"restaurant_id": "r_anker", "date": date, "party_size": 2}
        params.pop(drop)
        expect_error(req("GET", "/availability", params=params),
                     422, "validation_failed")
    for bad in ("2026-02-30", "not-a-date"):
        expect_error(req("GET", "/availability", params={
            "restaurant_id": "r_anker", "date": bad, "party_size": 2}),
            422, "validation_failed")
    for bad in ("0", "-1", "abc", "1e9", "4.0", "+4"):
        expect_error(req("GET", "/availability", params={
            "restaurant_id": "r_anker", "date": date, "party_size": bad}),
            422, "validation_failed")
    expect_error(req("GET", "/availability", params={
        "restaurant_id": "r_nope", "date": date, "party_size": 2}),
        404, "not_found")
    expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 2,
        "sort": "x"}), 200)


@check("closed day returns empty slots")
def _():
    date = book_date()
    weekday = WEEKDAYS[dt.date.fromisoformat(date).weekday()]
    closed = [h for h in all_week() if h["weekday"] != weekday]
    expect(reset(fixture(restaurants=[restaurant(opening_hours=closed)])), 204)
    body = expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 2}), 200)
    want(body["slots"] == [], "closed day must have no slots")


@check("booking happy path shape")
def _():
    expect(reset(), 204)
    token = login()
    body = expect(book(token), 201)
    want(set(body) >= {"reservation_id", "reference", "restaurant_id",
                       "table_id", "party_size", "status", "starts_at_local",
                       "starts_at", "ends_at", "created_at"},
         f"booking shape {sorted(body)}")
    want(REFERENCE_RE.match(body["reference"]), f"reference {body['reference']}")
    want(body["status"] == "confirmed", "status")
    want(body["starts_at_local"] == local(book_date(), "19:00"), "starts_at_local")
    for f in ("starts_at", "ends_at", "created_at"):
        want(OFFSET_RE.search(body[f]), f"{f} needs explicit offset")
    want(body["ends_at"].startswith(book_date() + "T20:30"), "ends_at 90min")


@check("overlap and adjacency rules")
def _():
    expect(reset(), 204)
    token = login()
    date = book_date()
    expect(book(token, date, "19:00"), 201)
    expect_error(book(token, date, "20:00"), 409, "table_unavailable")
    expect(book(token, date, "20:30"), 201)
    expect(book(token, date, "19:00", table_id="t_3"), 201)
    # Booked table leaves every overlapping slot.
    body = expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 4}), 200)
    by_time = {s["starts_at_local"].split("T")[1]: s["available_table_ids"]
               for s in body["slots"]}
    for t in ("18:00", "18:30", "19:00", "19:30", "20:00"):
        want("t_2" not in by_time[t], f"t_2 still offered at {t}")
    # t_3 ends at 20:30 exactly: a half-open occupancy means the 20:30 slot
    # must offer it again, while t_2 is now booked at 20:30 itself.
    want("t_3" in by_time["20:30"], "adjacent slot must be free")
    want("t_2" not in by_time["20:30"], "t_2 is occupied at 20:30")


@check("booking validation precedence")
def _():
    expect(reset(), 204)
    token = login()
    date = book_date()
    expect_error(book(token, date, "19:15"), 422, "not_on_slot_grid")
    expect_error(book(token, date, "17:00"), 422, "outside_opening_hours")
    expect_error(book(token, date, "22:00"), 422, "outside_opening_hours")
    expect_error(book(token, date, "19:00", table_id="t_1", party_size=4),
                 422, "party_exceeds_capacity")
    for bad in (0, -1, "4", 1.5, True):
        expect_error(book(token, date, "19:00", party_size=bad),
                     422, "validation_failed")
    for bad in ("2026-09-24T19:00:00", "2026-09-24T19:00Z",
                "2026-09-24T19:00:00+02:00", "not-a-time"):
        expect_error(req("POST", "/reservations", body={
            "restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": bad, "party_size": 4},
            token=token, key=new_key()), 422, "validation_failed")
    expect_error(book(token, date, "19:00", restaurant_id="r_nope"),
                 404, "not_found")
    expect_error(book(token, date, "19:00", table_id="t_nope"),
                 404, "not_found")
    expect(reset(fixture(restaurants=[
        restaurant(), restaurant("r_other", tables=[
            {"id": "t_x", "label": "X", "capacity": 4}])])), 204)
    token = login()
    expect_error(book(token, date, "19:00", table_id="t_x"), 404, "not_found")
    expect(reset(), 204)


@check("malformed json is 400")
def _():
    expect(reset(), 204)
    token = login()
    expect_error(req("POST", "/reservations", raw_body="{not json",
                     token=token, key=new_key()), 400, "malformed_request")


@check("cancel frees the slot; repeat cancel is 200")
def _():
    expect(reset(), 204)
    token, other = login(), login("bob@example.com", "correct horse")
    date = book_date()
    ref = expect(book(token, date), 201)["reference"]
    expect(req("POST", f"/reservations/{ref}/cancel", token=token), 200)
    body = expect(req("POST", f"/reservations/{ref}/cancel", token=token), 200)
    want(body["status"] == "cancelled", "second cancel returns current state")
    avail = expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 4}), 200)
    slot = next(s for s in avail["slots"]
                if s["starts_at_local"].endswith("19:00"))
    want("t_2" in slot["available_table_ids"], "cancel freed the table")
    ref2 = expect(book(token, date, "20:30"), 201)["reference"]
    expect_error(req("POST", f"/reservations/{ref2}/cancel", token=other),
                 404, "not_found")


@check("cutoff refuses cancel and amend")
def _():
    huge = restaurant(cancellation_cutoff_minutes=60 * 24 * 3650)
    expect(reset(fixture(restaurants=[huge])), 204)
    token = login()
    ref = expect(book(token), 201)["reference"]
    expect_error(req("POST", f"/reservations/{ref}/cancel", token=token),
                 409, "cutoff_passed")
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"party_size": 2}, token=token),
                 409, "cutoff_passed")
    # A booking already started is "later" than the cutoff too.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    expect(reset(fixture(reservations=[{
        "id": "res_seed", "reference": "SEED01", "user_id": "u_ada",
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": local(yesterday), "party_size": 4}])), 204)
    token = login()
    expect_error(req("POST", "/reservations/SEED01/cancel", token=token),
                 409, "cutoff_passed")


@check("patch amends; failed amend leaves state")
def _():
    expect(reset(), 204)
    token, other = login(), login("bob@example.com", "correct horse")
    date = book_date()
    expect(book(token, date, "19:00", table_id="t_3"), 201)
    created = expect(book(token, date, "19:00", table_id="t_2"), 201)
    ref = created["reference"]
    body = expect(req("PATCH", f"/reservations/{ref}",
                      body={"party_size": 3}, token=token), 200)
    want(body["reference"] == ref
         and body["reservation_id"] == created["reservation_id"],
         "patch must keep identity")
    want(body["party_size"] == 3, "party size changed")
    # Failed amendment leaves the booking untouched.
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"table_id": "t_3"}, token=token),
                 409, "table_unavailable")
    current = expect(req("GET", f"/reservations/{ref}", token=token), 200)
    want(current["table_id"] == "t_2" and current["party_size"] == 3,
         "failed patch must not change state")
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"starts_at_local": local(date, "19:15")},
                     token=token), 422, "not_on_slot_grid")
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"table_id": "t_nope"}, token=token), 404, "not_found")
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"party_size": 2}, token=other), 404, "not_found")
    expect(req("POST", f"/reservations/{ref}/cancel", token=token), 200)
    expect_error(req("PATCH", f"/reservations/{ref}",
                     body={"party_size": 2}, token=token),
                 409, "reservation_cancelled")


@check("reservation list is mine, starts_at descending, includes cancelled")
def _():
    expect(reset(), 204)
    token, other = login(), login("bob@example.com", "correct horse")
    date = book_date()
    for at in ("18:00", "21:00", "19:30"):
        expect(book(token, date, at), 201)
    expect(book(other, date, "18:00", table_id="t_3"), 201)
    mine = expect(req("GET", "/reservations", token=token), 200)["reservations"]
    want(len(mine) == 3 and all(r["table_id"] == "t_2" for r in mine),
         "list must contain only the caller's bookings")
    starts = [r["starts_at"] for r in mine]
    want(starts == sorted(starts, reverse=True), "descending order")
    ref = mine[0]["reference"]
    expect(req("POST", f"/reservations/{ref}/cancel", token=token), 200)
    statuses = {r["status"] for r in
                expect(req("GET", "/reservations", token=token), 200)["reservations"]}
    want("cancelled" in statuses, "cancelled entries stay in the list")
    expect_error(req("GET", "/reservations/ZZZZZZ", token=token),
                 404, "not_found")


@check("idempotency: replay, reuse, scoping")
def _():
    expect(reset(), 204)
    token, other = login(), login("bob@example.com", "correct horse")
    date = book_date()
    body = {"restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": local(date, "19:00"), "party_size": 4}
    # Missing header -> 400.
    expect_error(req("POST", "/reservations", body=body, token=token),
                 400, "missing_idempotency_key")
    expect_error(req("POST", "/reservations", body=body, token=token, key=""),
                 400, "missing_idempotency_key")
    expect_error(req("POST", "/reservations", body=body, token=token,
                     key="k" * 256), 422, "validation_failed")
    key = new_key()
    first = expect(req("POST", "/reservations", body=body, token=token, key=key),
                   201)
    replay = expect(req("POST", "/reservations", body=dict(
        reversed(list(body.items()))), token=token, key=key), 200)
    want(replay == first, "replay must return the identical body")
    expect_error(req("POST", "/reservations", body={**body, "party_size": 3},
                     token=token, key=key), 409, "idempotency_key_reuse")
    # Key scoped per user: another account may reuse the string.
    expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_3",
        "starts_at_local": local(date, "19:00"), "party_size": 4},
        token=other, key=key), 201)
    # Failed requests free the key.
    k2 = new_key()
    expect_error(req("POST", "/reservations", body={**body, "party_size": 0},
                     token=token, key=k2), 422, "validation_failed")
    expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_1",
        "starts_at_local": local(date, "19:00"), "party_size": 2},
        token=token, key=k2), 201)
    # Replay after cancel returns the original confirmed body.
    k3 = new_key()
    original = expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_3",
        "starts_at_local": local(date, "20:30"), "party_size": 4},
        token=token, key=k3), 201)
    expect(req("POST", f"/reservations/{original['reference']}/cancel",
               token=token), 200)
    again = expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_3",
        "starts_at_local": local(date, "20:30"), "party_size": 4},
        token=token, key=k3), 200)
    want(again == original and again["status"] == "confirmed",
         "replay returns the original receipt")


@check("concurrent identical posts create exactly one booking")
def _():
    expect(reset(), 204)
    token = login()
    date = book_date()
    key = new_key()
    body = {"restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": local(date, "19:00"), "party_size": 4}
    results = []

    def worker():
        results.append(req("POST", "/reservations", body=body,
                           token=token, key=key))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = sorted(s for s, _ in results)
    want(codes.count(201) == 1, f"expected exactly one 201, got {codes}")
    want(all(s == 200 for s in codes if s != 201),
         f"non-replay statuses in {codes}")
    bodies = {json.dumps(b, sort_keys=True) for _, b in results}
    want(len(bodies) == 1, "all responses must be the same body")
    mine = expect(req("GET", "/reservations", token=token), 200)["reservations"]
    want(len(mine) == 1, "the operation must take effect exactly once")


@check("concurrent conflicting bookings: exactly one wins")
def _():
    expect(reset(), 204)
    token = login()
    date = book_date()
    results = []

    def worker(i):
        results.append(book(token, date, "19:00", table_id="t_2"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = sorted(s for s, _ in results)
    want(codes.count(201) == 1, f"exactly one booking may win: {codes}")
    want(codes.count(409) == 15, f"rest must be 409: {codes}")
    for s, b in results:
        if s == 409:
            want(b["error"]["code"] == "table_unavailable", "409 code")


@check("reservation-moves: atomic success and failure rollback")
def _():
    expect(reset(), 204)
    token, other = login(), login("bob@example.com", "correct horse")
    date = book_date()
    r1 = expect(book(token, date, "19:00", table_id="t_2", party_size=2),
                201)["reference"]
    r2 = expect(book(token, date, "20:30", table_id="t_3", party_size=4),
                201)["reference"]
    moves = {"moves": [{"reference": r1, "table_id": "t_1"},
                       {"reference": r2, "table_id": "t_2"}]}
    key = new_key()
    status, body = req("POST", "/reservation-moves", body=moves,
                       token=token, key=key)
    want(status == 201, f"moves -> {status}: {body!r}")
    want([r["reference"] for r in body["reservations"]] == [r1, r2],
         "reservations in input order")
    want(body["reservations"][0]["table_id"] == "t_1"
         and body["reservations"][1]["table_id"] == "t_2", "moves applied")
    replay = expect(req("POST", "/reservation-moves", body=moves,
                        token=token, key=key), 200)
    want(replay == body, "moves replay returns original body")
    # Failure leaves every booking unchanged.
    bad = {"moves": [{"reference": r1, "table_id": "t_2"},
                     {"reference": r2, "party_size": 99}]}
    expect_error(req("POST", "/reservation-moves", body=bad,
                     token=token, key=new_key()), 422, "party_exceeds_capacity")
    cur = expect(req("GET", f"/reservations/{r1}", token=token), 200)
    want(cur["table_id"] == "t_1", "failed batch must not move r1")
    # Shape and ownership rules.
    expect_error(req("POST", "/reservation-moves", body={"moves": []},
                     token=token, key=new_key()), 422, "validation_failed")
    expect_error(req("POST", "/reservation-moves",
                     body={"moves": [{"reference": r1}, {"reference": r1}]},
                     token=token, key=new_key()), 422, "validation_failed")
    expect_error(req("POST", "/reservation-moves",
                     body={"moves": [{"reference": r1}]},
                     token=other, key=new_key()), 404, "not_found")
    expect_error(req("POST", "/reservation-moves", body=moves, token=token),
                 400, "missing_idempotency_key")
    expect_error(req("POST", "/reservation-moves",
                     body={"moves": [{"reference": "NOPE12"}]},
                     token=token, key=new_key()), 404, "not_found")
    # Two bookings swapped onto each other's tables in one batch: each one's
    # new table is the other's old table, freed by the same batch.
    r3 = expect(book(token, date, "18:00", table_id="t_2", party_size=2),
                201)["reference"]
    r4 = expect(book(token, date, "18:00", table_id="t_3", party_size=2),
                201)["reference"]
    swap = {"moves": [{"reference": r3, "table_id": "t_3"},
                      {"reference": r4, "table_id": "t_2"}]}
    expect(req("POST", "/reservation-moves", body=swap, token=token,
               key=new_key()), 201)


@check("export/import preserves credentials, receipts and state")
def _():
    expect(reset(), 204)
    token = login()
    date = book_date()
    key = new_key()
    made = expect(book(token, date, "19:00", key=key), 201)
    status, export = req("GET", "/_test/export")
    want(status == 200 and export.get("track") == "tablekeeper"
         and export.get("format_version") == 1 and "state" in export,
         f"export shape {sorted(export or {})}")
    # Mutate: a second booking, then import the earlier snapshot.
    expect(book(token, date, "20:30"), 201)
    expect(req("POST", "/_test/import", body=export), 204)
    mine = expect(req("GET", "/reservations", token=token), 200)["reservations"]
    want([r["reference"] for r in mine] == [made["reference"]],
         "import must restore the snapshot, not merge")
    # Token survived the import; replay returns the original receipt.
    replay = expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": local(date, "19:00"), "party_size": 4},
        token=token, key=key), 200)
    want(replay == made, "receipt preserved across import")
    # Login still works with the seeded password after import.
    login()
    # Bad imports are refused without changing state.
    expect_error(req("POST", "/_test/import", body={"track": "nope"}),
                 422, "validation_failed")
    expect(req("GET", "/reservations", token=token), 200)
    expect(reset(), 204)


@check("DST: skipped hour invalid, repeated hour first occurrence")
def _():
    around = restaurant(opening_hours=all_week("00:00", "23:30"))
    expect(reset(fixture(restaurants=[around])), 204)
    token = login()
    expect_error(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": "2026-03-29T02:30", "party_size": 4},
        token=token, key=new_key()), 422, "invalid_local_time")
    avail = expect(req("GET", "/availability", params={
        "restaurant_id": "r_anker", "date": "2026-10-25", "party_size": 4}),
        200)
    times = [s["starts_at_local"].split("T")[1] for s in avail["slots"]]
    want(times.count("02:00") == 1 and times.count("02:30") == 1,
         f"repeated hour must appear once: {times}")
    body = expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": "2026-10-25T02:00", "party_size": 4},
        token=token, key=new_key()), 201)
    want(body["starts_at"].endswith("+02:00"),
         f"first occurrence is CEST: {body['starts_at']}")
    early = expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_3",
        "starts_at_local": "2026-10-25T01:30", "party_size": 4},
        token=token, key=new_key()), 201)
    want("T02:00" in early["ends_at"],
         f"90 real minutes from 01:30 ends 02:00 local: {early['ends_at']}")
    expect(reset(), 204)


@check("unknown fields are ignored")
def _():
    expect(reset(), 204)
    token = login()
    expect(req("POST", "/reservations", body={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": local(book_date(), "19:00"), "party_size": 4,
        "souvenir": "yes"}, token=token, key=new_key()), 201)


@check("hardened mode note: test endpoints respond on the judge image")
def _():
    # Documents the default mode: /_test/* are enabled. A TK_HARDENED=1
    # deployment must 404 them instead (see RUN.md); this check only runs
    # against the default image.
    expect(reset(), 204)


def main():
    print(f"local checks against {BASE_URL}")
    print(f"{_checks - len(_failures)} passed, {len(_failures)} failed "
          f"of {_checks}")
    if _failures:
        print("failed:", ", ".join(_failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
