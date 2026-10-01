"""Spec-derived HTTP tests for the Tablekeeper stage-1 service.

Run from stage-1/:  python -m unittest discover -s tests -v
(or: python tests/test_api.py)

Spins the real server on an ephemeral port; each test reseeds via
POST /_test/reset. Dates are chosen to keep cutoff maths deterministic:
far-future dates for cancellable bookings, past dates for cutoff_passed.
"""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import server  # noqa: E402
import state  # noqa: E402

BASE = None
_SERVER = None


def setUpModule():
    global BASE, _SERVER
    from http.server import ThreadingHTTPServer
    _SERVER = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _SERVER.daemon_threads = True
    BASE = "http://127.0.0.1:%d" % _SERVER.server_address[1]
    threading.Thread(target=_SERVER.serve_forever, daemon=True).start()


def tearDownModule():
    _SERVER.shutdown()
    _SERVER.server_close()


def req(method, path, body="skip", token=None, key=None, raw=None,
        headers=None):
    url = BASE + path
    data = None
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode()
    elif body != "skip":
        data = json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if key is not None:
        r.add_header("Idempotency-Key", key)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        payload = resp.read()
        return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return e.code, {"_raw": payload[:200].decode("utf-8", "replace")}


def fixture(**over):
    fx = {
        "users": [
            {"id": "u_ada", "email": "ada@example.com",
             "password": "correct horse", "display_name": "Ada"},
            {"id": "u_bob", "email": "bob@example.com",
             "password": "correct horse", "display_name": "Bob"},
        ],
        "restaurants": [
            {
                "id": "r_anker", "name": "Zum Anker",
                "timezone": "Europe/Berlin",
                "slot_minutes": 30, "reservation_duration_minutes": 90,
                "cancellation_cutoff_minutes": 120,
                "opening_hours": [
                    {"weekday": w, "opens": "08:00", "closes": "22:00"}
                    for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                ],
                "tables": [
                    {"id": "t_1", "label": "1", "capacity": 2},
                    {"id": "t_2", "label": "2", "capacity": 4},
                    {"id": "t_3", "label": "3", "capacity": 6},
                ],
            },
            {
                "id": "r_dst", "name": "DST House",
                "timezone": "Europe/Berlin",
                "slot_minutes": 30, "reservation_duration_minutes": 90,
                "cancellation_cutoff_minutes": 60,
                "opening_hours": [
                    {"weekday": "sun", "opens": "00:00", "closes": "06:00"},
                ],
                "tables": [{"id": "t_d", "label": "d", "capacity": 4}],
            },
            {
                "id": "r_ny", "name": "NYC Diner",
                "timezone": "America/New_York",
                "slot_minutes": 60, "reservation_duration_minutes": 60,
                "cancellation_cutoff_minutes": 60,
                "opening_hours": [
                    {"weekday": "wed", "opens": "12:00", "closes": "20:00"},
                ],
                "tables": [{"id": "t_ny", "label": "n", "capacity": 8}],
            },
        ],
        "reservations": [],
    }
    fx.update(over)
    return fx


def reset(fx=None):
    status, body = req("POST", "/_test/reset", body=fx or fixture())
    assert status == 204, (status, body)


def signup(email="new@example.com", password="longpassword",
           display_name="New"):
    return req("POST", "/auth/signup",
               body={"email": email, "password": password,
                     "display_name": display_name})


def login(email="ada@example.com", password="correct horse"):
    return req("POST", "/auth/login",
               body={"email": email, "password": password})


def token_for(email="ada@example.com"):
    s, b = login(email)
    assert s == 200, (s, b)
    return b["token"]


def book(token, key, table="t_2", local="2030-06-05T19:00", party=4,
         rest="r_anker"):
    return req("POST", "/reservations", token=token, key=key, body={
        "restaurant_id": rest, "table_id": table,
        "starts_at_local": local, "party_size": party})


def errcode(body):
    return body["error"]["code"]


class HealthAndMeta(unittest.TestCase):
    def test_health(self):
        s, b = req("GET", "/health")
        self.assertEqual((s, b), (200, {"status": "ok"}))

    def test_unknown_route_404_json(self):
        s, b = req("GET", "/nope")
        self.assertEqual(s, 404)
        self.assertEqual(errcode(b), "not_found")

    def test_post_restaurants_is_404(self):
        s, b = req("POST", "/restaurants", body={})
        self.assertEqual(s, 404)

    def test_error_shape(self):
        s, b = req("GET", "/reservations")
        self.assertEqual(s, 401)
        self.assertIn("code", b["error"])
        self.assertIn("message", b["error"])


class ResetAndFixture(unittest.TestCase):
    def setUp(self):
        reset()

    def test_reset_204_and_repeatable(self):
        s, _ = req("POST", "/_test/reset", body=fixture())
        self.assertEqual(s, 204)
        s, _ = req("POST", "/_test/reset", body=fixture())
        self.assertEqual(s, 204)

    def test_reset_bad_fixture_422(self):
        s, b = req("POST", "/_test/reset",
                   body={"restaurants": [{"id": "x", "opening_hours": [
                       {"weekday": "noday", "opens": "10:00",
                        "closes": "11:00"}]}]})
        self.assertEqual(s, 422)
        self.assertEqual(errcode(b), "validation_failed")

    def test_reset_overlength_id_422(self):
        fx = fixture(restaurants=[{
            "id": "x" * 65, "name": "x", "timezone": "Europe/Berlin",
            "slot_minutes": 30, "reservation_duration_minutes": 60,
            "cancellation_cutoff_minutes": 0, "opening_hours": [],
            "tables": []}])
        s, b = req("POST", "/_test/reset", body=fx)
        self.assertEqual(s, 422)

    def test_reset_closes_not_after_opens_422(self):
        fx = fixture(restaurants=[{
            "id": "r1", "name": "x", "timezone": "Europe/Berlin",
            "slot_minutes": 30, "reservation_duration_minutes": 60,
            "cancellation_cutoff_minutes": 0,
            "opening_hours": [{"weekday": "mon", "opens": "10:00",
                               "closes": "10:00"}],
            "tables": []}])
        s, b = req("POST", "/_test/reset", body=fx)
        self.assertEqual(s, 422)

    def test_reset_replaces_state(self):
        tok = token_for()
        reset(fixture(users=[{"id": "u_c", "email": "c@example.com",
                              "password": "correct horse",
                              "display_name": "C"}]))
        s, _ = req("GET", "/reservations", token=tok)
        self.assertEqual(s, 401)  # old token dead after reset
        s, b = login("c@example.com")
        self.assertEqual(s, 200)

    def test_seeded_reservation_visible(self):
        fx = fixture(reservations=[{
            "id": "res_seed", "reference": "SEED01", "user_id": "u_ada",
            "restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": "2030-06-05T19:00", "party_size": 2}])
        reset(fx)
        tok = token_for()
        s, b = req("GET", "/reservations", token=tok)
        self.assertEqual(s, 200)
        self.assertEqual(len(b["reservations"]), 1)
        self.assertEqual(b["reservations"][0]["reference"], "SEED01")
        self.assertEqual(b["reservations"][0]["status"], "confirmed")


class Auth(unittest.TestCase):
    def setUp(self):
        reset()

    def test_signup_shape(self):
        s, b = signup()
        self.assertEqual(s, 201)
        self.assertTrue(set(b) >= {"user_id", "display_name", "token"})

    def test_signup_duplicate_email_409(self):
        signup("dup@example.com")
        s, b = signup("dup@example.com")
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "email_taken")

    def test_signup_duplicate_email_case_insensitive(self):
        signup("Ada@X.com")
        s, b = signup("ada@x.com")
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "email_taken")

    def test_signup_short_password_422(self):
        s, b = signup(password="short")
        self.assertEqual(s, 422)
        self.assertEqual(errcode(b), "validation_failed")

    def test_signup_bad_email_422(self):
        for bad in ("a@", "@b.com", "a@b", "no-at", "a b@c.com", "a@@b.com"):
            s, b = signup(email=bad)
            self.assertEqual(s, 422, bad)
            self.assertEqual(errcode(b), "validation_failed")

    def test_login_ok_and_wrong(self):
        s, b = login()
        self.assertEqual(s, 200)
        self.assertEqual(b["display_name"], "Ada")
        s, b = login(password="wrong password")
        self.assertEqual(s, 401)
        self.assertEqual(errcode(b), "unauthenticated")
        s, b = login("nobody@example.com")
        self.assertEqual(s, 401)

    def test_multiple_tokens(self):
        t1, t2 = token_for(), token_for()
        self.assertNotEqual(t1, t2)
        self.assertEqual(req("GET", "/reservations", token=t1)[0], 200)
        self.assertEqual(req("GET", "/reservations", token=t2)[0], 200)

    def test_bearer_variants_401(self):
        self.assertEqual(req("GET", "/reservations")[0], 401)
        self.assertEqual(req("GET", "/reservations", token="bogus")[0], 401)
        s, _ = req("GET", "/reservations",
                   headers={"Authorization": "Basic abc"})
        self.assertEqual(s, 401)

    def test_public_endpoints_no_auth(self):
        self.assertEqual(req("GET", "/restaurants")[0], 200)
        self.assertEqual(req("GET", "/restaurants/r_anker")[0], 200)
        s, _ = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-06-05&party_size=2")
        self.assertEqual(s, 200)


class AvailabilityAndRestaurants(unittest.TestCase):
    def setUp(self):
        reset()

    def test_restaurants_list_shape(self):
        s, b = req("GET", "/restaurants")
        self.assertEqual(s, 200)
        first = b["restaurants"][0]
        self.assertEqual(set(first), {"id", "name", "timezone"})
        self.assertEqual(first["id"], "r_anker")

    def test_restaurant_detail(self):
        s, b = req("GET", "/restaurants/r_anker")
        self.assertEqual(s, 200)
        self.assertEqual(b["slot_minutes"], 30)
        self.assertEqual(len(b["tables"]), 3)
        s, _ = req("GET", "/restaurants/nope")
        self.assertEqual(s, 404)

    def test_availability_grid(self):
        s, b = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-06-05&party_size=2")
        self.assertEqual(s, 200)
        self.assertEqual(b["timezone"], "Europe/Berlin")
        locals_ = [sl["starts_at_local"] for sl in b["slots"]]
        self.assertEqual(locals_[0], "2030-06-05T08:00")
        # last start: 22:00 - 90min = 20:30
        self.assertEqual(locals_[-1], "2030-06-05T20:30")
        self.assertEqual(len(locals_), ((20 * 60 + 30) - 8 * 60) // 30 + 1)
        self.assertEqual(b["slots"][0]["starts_at"],
                         "2030-06-05T08:00:00+02:00")
        self.assertEqual(b["slots"][0]["available_table_ids"],
                         ["t_1", "t_2", "t_3"])

    def test_availability_party_filters_tables(self):
        s, b = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-06-05&party_size=5")
        self.assertEqual(b["slots"][0]["available_table_ids"], ["t_3"])

    def test_availability_missing_and_bad_params(self):
        for q in ("date=2030-06-05&party_size=2",
                  "restaurant_id=r_anker&party_size=2",
                  "restaurant_id=r_anker&date=2030-06-05"):
            s, b = req("GET", "/availability?" + q)
            self.assertEqual(s, 422, q)
        for p in ("1e9", "4.0", "+4", "-2", "x", "0", ""):
            s, b = req("GET", "/availability?restaurant_id=r_anker"
                              "&date=2030-06-05&party_size=" + p)
            self.assertEqual(s, 422, p)
        s, _ = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-13-40&party_size=2")
        self.assertEqual(s, 422)
        s, _ = req("GET", "/availability?restaurant_id=nope"
                          "&date=2030-06-05&party_size=2")
        self.assertEqual(s, 404)

    def test_availability_closed_day(self):
        s, b = req("GET", "/availability?restaurant_id=r_ny"
                          "&date=2030-06-04&party_size=2")  # Tuesday: closed
        self.assertEqual(s, 200)
        self.assertEqual(b["slots"], [])

    def test_availability_reflects_bookings(self):
        tok = token_for()
        s, b = book(tok, "k-av", "t_1", "2030-06-05T19:00", 2)
        self.assertEqual(s, 201)
        s, b = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-06-05&party_size=2")
        slot = [sl for sl in b["slots"]
                if sl["starts_at_local"] == "2030-06-05T19:00"][0]
        self.assertEqual(slot["available_table_ids"], ["t_2", "t_3"])


class Reservations(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()

    def test_create_shape(self):
        s, b = book(self.tok, "k1")
        self.assertEqual(s, 201)
        self.assertEqual(b["status"], "confirmed")
        self.assertRegex(b["reference"], r"^[A-Z0-9]{6,12}$")
        self.assertEqual(b["starts_at"], "2030-06-05T19:00:00+02:00")
        self.assertEqual(b["ends_at"], "2030-06-05T20:30:00+02:00")
        self.assertTrue(b["created_at"].endswith("+00:00"))

    def test_half_open_boundary(self):
        s, _ = book(self.tok, "k2", "t_1", "2030-06-05T19:00", 2)
        self.assertEqual(s, 201)
        # 19:00+90min ends 20:30; a 20:30 booking must NOT conflict
        s, _ = book(self.tok, "k3", "t_1", "2030-06-05T20:30", 2)
        self.assertEqual(s, 201)
        # but 20:00 overlaps the 19:00-20:30 interval
        s, b = book(self.tok, "k4", "t_1", "2030-06-05T20:00", 2)
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "table_unavailable")

    def test_validation_errors(self):
        cases = [
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:15",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "not_on_slot_grid"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T06:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "outside_opening_hours"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T21:30",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "outside_opening_hours"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": 5, "restaurant_id": "r_anker"},
             422, "party_exceeds_capacity"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": "4", "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": True, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": 0, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": 2.0, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1",
              "starts_at_local": "2030-06-05T19:00:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1",
              "starts_at_local": "2030-06-05T19:00+02:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05 19:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             422, "validation_failed"),
            ({"table_id": "t_zz", "starts_at_local": "2030-06-05T19:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             404, "not_found"),
            ({"table_id": "t_ny", "starts_at_local": "2030-06-05T19:00",
              "party_size": 2, "restaurant_id": "r_anker"},
             404, "not_found"),
            ({"table_id": "t_1", "starts_at_local": "2030-06-05T19:00",
              "party_size": 2, "restaurant_id": "r_nope"},
             404, "not_found"),
        ]
        for i, (body, status, code) in enumerate(cases):
            s, b = req("POST", "/reservations", token=self.tok,
                       key="bad-%d" % i, body=body)
            self.assertEqual((s, errcode(b)), (status, code), body)

    def test_missing_field_422(self):
        s, b = req("POST", "/reservations", token=self.tok, key="mf",
                   body={"restaurant_id": "r_anker", "table_id": "t_1",
                         "starts_at_local": "2030-06-05T19:00"})
        self.assertEqual(s, 422)
        self.assertEqual(errcode(b), "validation_failed")

    def test_wrong_type_400(self):
        s, b = req("POST", "/reservations", token=self.tok, key="wt",
                   body={"restaurant_id": 5, "table_id": "t_1",
                         "starts_at_local": "2030-06-05T19:00",
                         "party_size": 2})
        self.assertEqual(s, 400)
        self.assertEqual(errcode(b), "malformed_request")

    def test_unparseable_and_nonobject_400(self):
        s, b = req("POST", "/reservations", token=self.tok, key="np",
                   raw="{not json")
        self.assertEqual((s, errcode(b)), (400, "malformed_request"))
        s, b = req("POST", "/reservations", token=self.tok, key="np2",
                   raw="[1,2]")
        self.assertEqual(s, 400)

    def test_unknown_fields_ignored(self):
        s, b = req("POST", "/reservations", token=self.tok, key="uf",
                   body={"restaurant_id": "r_anker", "table_id": "t_1",
                         "starts_at_local": "2030-06-05T19:00",
                         "party_size": 2, "extra": "x", "id": "hax"})
        self.assertEqual(s, 201)
        self.assertNotEqual(b["reservation_id"], "hax")

    def test_past_booking_allowed(self):
        s, b = book(self.tok, "past", local="2020-06-04T19:00")
        self.assertEqual(s, 201)

    def test_list_ordering_and_isolation(self):
        book(self.tok, "o1", "t_1", "2030-06-05T19:00", 2)
        book(self.tok, "o2", "t_1", "2030-06-06T18:00", 2)
        book(self.tok, "o3", "t_1", "2030-06-04T18:00", 2)
        s, b = req("GET", "/reservations", token=self.tok)
        starts = [r["starts_at"] for r in b["reservations"]]
        self.assertEqual(starts, sorted(starts, reverse=True))
        other = token_for("bob@example.com")
        s, b = req("GET", "/reservations", token=other)
        self.assertEqual(b["reservations"], [])

    def test_get_one_and_foreign_404(self):
        s, b = book(self.tok, "g1")
        ref = b["reference"]
        s, b = req("GET", "/reservations/" + ref, token=self.tok)
        self.assertEqual(s, 200)
        other = token_for("bob@example.com")
        s, _ = req("GET", "/reservations/" + ref, token=other)
        self.assertEqual(s, 404)

    def test_cancel(self):
        s, b = book(self.tok, "c1")
        ref = b["reference"]
        s, b = req("POST", "/reservations/%s/cancel" % ref,
                   token=self.tok, body={})
        self.assertEqual(s, 200)
        self.assertEqual(b["status"], "cancelled")
        # double cancel -> 200
        s, b = req("POST", "/reservations/%s/cancel" % ref,
                   token=self.tok, body={})
        self.assertEqual(s, 200)
        # slot freed
        s, b = book(self.tok, "c2", "t_2", "2030-06-05T19:00", 4)
        self.assertEqual(s, 201)
        # foreign cancel -> 404
        other = token_for("bob@example.com")
        s, _ = req("POST", "/reservations/%s/cancel" % ref, token=other,
                   body={})
        self.assertEqual(s, 404)

    def test_cancel_cutoff(self):
        s, b = book(self.tok, "cc", local="2020-06-04T19:00")
        ref = b["reference"]
        s, b = req("POST", "/reservations/%s/cancel" % ref,
                   token=self.tok, body={})
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "cutoff_passed")

    def test_patch(self):
        s, b = book(self.tok, "p1", "t_1", "2030-06-05T18:00", 2)
        ref = b["reference"]
        rid = b["reservation_id"]
        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"table_id": "t_2", "party_size": 4,
                         "starts_at_local": "2030-06-05T19:30"})
        self.assertEqual(s, 200)
        self.assertEqual(b["table_id"], "t_2")
        self.assertEqual(b["party_size"], 4)
        self.assertEqual(b["starts_at_local"], "2030-06-05T19:30")
        self.assertEqual(b["reference"], ref)
        self.assertEqual(b["reservation_id"], rid)

    def test_patch_failed_leaves_occupancy(self):
        s, b = book(self.tok, "p2a", "t_1", "2030-06-05T18:00", 2)
        ref_a = b["reference"]
        book(self.tok, "p2b", "t_2", "2030-06-05T18:00", 4)
        # move A onto t_2 18:00 -> taken -> 409, A keeps t_1
        s, b = req("PATCH", "/reservations/" + ref_a, token=self.tok,
                   body={"table_id": "t_2"})
        self.assertEqual(s, 409)
        s, b = book(self.tok, "p2c", "t_1", "2030-06-05T19:00", 2)
        self.assertEqual(s, 409)  # A still occupies t_1 18:00-19:30
        s, b = req("GET", "/reservations/" + ref_a, token=self.tok)
        self.assertEqual(b["table_id"], "t_1")

    def test_patch_cancelled_and_cutoff(self):
        s, b = book(self.tok, "p3", "t_1", "2030-06-05T18:00", 2)
        ref = b["reference"]
        req("POST", "/reservations/%s/cancel" % ref, token=self.tok, body={})
        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"party_size": 2})
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "reservation_cancelled")

        s, b = book(self.tok, "p4", "t_1", "2020-06-04T18:00", 2)
        s, b = req("PATCH", "/reservations/" + b["reference"],
                   token=self.tok, body={"party_size": 2})
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "cutoff_passed")

    def test_patch_foreign_404(self):
        s, b = book(self.tok, "p5")
        other = token_for("bob@example.com")
        s, _ = req("PATCH", "/reservations/" + b["reference"], token=other,
                   body={"party_size": 2})
        self.assertEqual(s, 404)


class Idempotency(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()
        self.body = {"restaurant_id": "r_anker", "table_id": "t_1",
                     "starts_at_local": "2030-06-05T19:00", "party_size": 2}

    def test_parse_beats_auth(self):
        # malformed body + no token -> 400 malformed_request (parse first)
        s, b = req("POST", "/reservations", raw="{not json")
        self.assertEqual((s, errcode(b)), (400, "malformed_request"))
        # non-object body + no token -> also a parse-level failure
        s, b = req("POST", "/reservations", raw="[1,2]")
        self.assertEqual(s, 400)
        # valid body + no token -> 401 (auth after parse)
        s, b = req("POST", "/reservations", body=self.body)
        self.assertEqual((s, errcode(b)), (401, "unauthenticated"))
        # valid body + token + no key -> 400 missing key
        s, b = req("POST", "/reservations", body=self.body, token=self.tok)
        self.assertEqual((s, errcode(b)), (400, "missing_idempotency_key"))

    def test_whitespace_key_is_valid(self):
        # G-10: a whitespace-only key is a valid key, never trimmed
        body = dict(self.body, table_id="t_3")
        s, b = req("POST", "/reservations", token=self.tok, body=body,
                   headers={"Idempotency-Key": " "})
        self.assertEqual(s, 201)
        s, b2 = req("POST", "/reservations", token=self.tok, body=body,
                    headers={"Idempotency-Key": " "})
        self.assertEqual(s, 200)
        self.assertEqual(b, b2)

    def test_missing_and_long_key(self):
        s, b = req("POST", "/reservations", token=self.tok, body=self.body)
        self.assertEqual((s, errcode(b)), (400, "missing_idempotency_key"))
        s, b = req("POST", "/reservations", token=self.tok, key="",
                   body=self.body)
        self.assertEqual(s, 400)
        s, b = req("POST", "/reservations", token=self.tok, key="k" * 256,
                   body=self.body)
        self.assertEqual((s, errcode(b)), (422, "validation_failed"))
        s, b = req("POST", "/reservations", token=self.tok, key="k" * 255,
                   body=self.body)
        self.assertEqual(s, 201)

    def test_replay_returns_200_original(self):
        s1, b1 = req("POST", "/reservations", token=self.tok, key="r1",
                     body=self.body)
        s2, b2 = req("POST", "/reservations", token=self.tok, key="r1",
                     body=dict(self.body))
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(b1, b2)
        # reorder keys in the replay body
        reordered = dict(reversed(list(self.body.items())))
        s3, b3 = req("POST", "/reservations", token=self.tok, key="r1",
                     body=reordered)
        self.assertEqual((s3, b3), (200, b1))

    def test_replay_after_cancel(self):
        s1, b1 = req("POST", "/reservations", token=self.tok, key="rc",
                     body=self.body)
        req("POST", "/reservations/%s/cancel" % b1["reference"],
            token=self.tok, body={})
        s2, b2 = req("POST", "/reservations", token=self.tok, key="rc",
                     body=self.body)
        self.assertEqual(s2, 200)
        self.assertEqual(b2, b1)
        self.assertEqual(b2["status"], "confirmed")

    def test_different_body_same_key_409(self):
        req("POST", "/reservations", token=self.tok, key="d1",
            body=self.body)
        other = dict(self.body, party_size=3)
        s, b = req("POST", "/reservations", token=self.tok, key="d1",
                   body=other)
        self.assertEqual((s, errcode(b)), (409, "idempotency_key_reuse"))

    def test_diff_body_invalid_still_409(self):
        req("POST", "/reservations", token=self.tok, key="d2",
            body=self.body)
        s, b = req("POST", "/reservations", token=self.tok, key="d2",
                   body={"garbage": True})
        self.assertEqual((s, errcode(b)), (409, "idempotency_key_reuse"))

    def test_failed_key_reusable(self):
        bad = dict(self.body, table_id="nope")
        s, _ = req("POST", "/reservations", token=self.tok, key="f1",
                   body=bad)
        self.assertEqual(s, 404)
        s, _ = req("POST", "/reservations", token=self.tok, key="f1",
                   body=self.body)
        self.assertEqual(s, 201)

    def test_same_key_other_user(self):
        other = token_for("bob@example.com")
        req("POST", "/reservations", token=self.tok, key="shared",
            body=self.body)
        s, _ = req("POST", "/reservations", token=other, key="shared",
                   body=self.body)
        self.assertEqual(s, 409)  # same table+time -> unavailable, not replay

    def test_same_key_other_path_succeeds(self):
        req("POST", "/reservations", token=self.tok, key="xp",
            body=self.body)
        s, b = req("POST", "/reservation-moves", token=self.tok, key="xp",
                   body={"moves": [{"reference": "ZZZZZZ"}]})
        self.assertEqual(s, 404)  # processed normally -> not replay/409-reuse

    def test_concurrent_identical(self):
        results = []
        lock = threading.Lock()

        def worker():
            s, b = req("POST", "/reservations", token=self.tok, key="race",
                       body=self.body)
            with lock:
                results.append(s)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(200), 19)
        s, b = req("GET", "/reservations", token=self.tok)
        self.assertEqual(len(b["reservations"]), 1)


class Dst(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()

    def test_spring_forward_gap(self):
        # Berlin 2026-03-29: 02:00->03:00 skipped; sun hours 00:00-06:00
        s, b = req("GET", "/availability?restaurant_id=r_dst"
                          "&date=2026-03-29&party_size=2")
        locals_ = [sl["starts_at_local"] for sl in b["slots"]]
        self.assertNotIn("2026-03-29T02:00", locals_)
        self.assertNotIn("2026-03-29T02:30", locals_)
        self.assertIn("2026-03-29T01:30", locals_)
        self.assertIn("2026-03-29T03:00", locals_)
        slot = [sl for sl in b["slots"]
                if sl["starts_at_local"] == "2026-03-29T01:30"][0]
        self.assertEqual(slot["starts_at"], "2026-03-29T01:30:00+01:00")
        # booking a nonexistent local -> 422 invalid_local_time
        s, b = book(self.tok, "dst1", "t_d", "2026-03-29T02:30", 2, "r_dst")
        self.assertEqual(s, 422)
        self.assertEqual(errcode(b), "invalid_local_time")

    def test_fall_back_first_occurrence(self):
        # Berlin 2026-10-25: 03:00->02:00 repeated; 02:30 -> +02:00
        s, b = book(self.tok, "dst2", "t_d", "2026-10-25T02:30", 2, "r_dst")
        self.assertEqual(s, 201)
        self.assertEqual(b["starts_at"], "2026-10-25T02:30:00+02:00")

    def test_absolute_duration_fall_back(self):
        # 01:30 + 90 real minutes on fall-back night ends 02:00 local
        s, b = book(self.tok, "dst3", "t_d", "2026-10-25T01:30", 2, "r_dst")
        self.assertEqual(s, 201)
        self.assertEqual(b["ends_at"], "2026-10-25T02:00:00+01:00")

    def test_ambiguous_slot_once(self):
        s, b = req("GET", "/availability?restaurant_id=r_dst"
                          "&date=2026-10-25&party_size=2")
        locals_ = [sl["starts_at_local"] for sl in b["slots"]]
        self.assertEqual(locals_.count("2026-10-25T02:30"), 1)

    def test_new_york_transitions(self):
        s, b = book(self.tok, "ny1", "t_ny", "2026-11-01T12:00", 2, "r_ny")
        # 2026-11-01 is a Sunday; r_ny open only Wednesday -> closed
        self.assertEqual(s, 422)
        self.assertEqual(errcode(b), "outside_opening_hours")
        # NY fall-back Sunday availability on a NY-open weekday is covered
        # by the Berlin tests; check a valid Wednesday booking offset -05
        s, b = book(self.tok, "ny2", "t_ny", "2026-11-04T12:00", 2, "r_ny")
        self.assertEqual(s, 201)
        self.assertEqual(b["starts_at"], "2026-11-04T12:00:00-05:00")


class Moves(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()
        _, a = book(self.tok, "m-a", "t_1", "2030-06-05T18:00", 2)
        _, b = book(self.tok, "m-b", "t_2", "2030-06-05T19:00", 4)
        self.ra, self.rb = a["reference"], b["reference"]

    def move(self, moves, key="mv"):
        return req("POST", "/reservation-moves", token=self.tok, key=key,
                   body={"moves": moves})

    def test_swap_tables(self):
        s, b = self.move([{"reference": self.ra, "table_id": "t_3"},
                          {"reference": self.rb, "table_id": "t_1",
                           "party_size": 2}])
        self.assertEqual(s, 201)
        self.assertEqual([r["reference"] for r in b["reservations"]],
                         [self.ra, self.rb])
        self.assertEqual(b["reservations"][0]["table_id"], "t_3")
        self.assertEqual(b["reservations"][1]["table_id"], "t_1")
        self.assertEqual(b["reservations"][1]["party_size"], 2)

    def test_noop_move(self):
        s, b = self.move([{"reference": self.ra}])
        self.assertEqual(s, 201)
        self.assertEqual(b["reservations"][0]["table_id"], "t_1")

    def test_shape_errors(self):
        # G-3: wrong JSON type for `moves` itself -> 400 malformed_request
        for bad in ("x", 4, None, {}):
            s, b = req("POST", "/reservation-moves", token=self.tok,
                       key="sh-type-%s" % bad, body={"moves": bad})
            self.assertEqual((s, errcode(b)), (400, "malformed_request"),
                             bad)
        for body, msg in [
                ({}, "missing"),
                ({"moves": []}, "empty"),
                ({"moves": [{"reference": "X"}] * 9}, "too many"),
                ({"moves": [{"reference": self.ra},
                            {"reference": self.ra}]}, "dup"),
                ({"moves": [{"reference": 5}]}, "non-string ref"),
                ({"moves": ["x"]}, "non-object item")]:
            s, b = req("POST", "/reservation-moves", token=self.tok,
                       key="sh-" + msg, body=body)
            self.assertEqual(s, 422, msg)
            self.assertEqual(errcode(b), "validation_failed")

    def test_unknown_and_foreign_refs(self):
        s, b = self.move([{"reference": "NOPE99", "party_size": 2}],
                         key="u1")
        self.assertEqual(s, 404)
        other = token_for("bob@example.com")
        _, ob = book(other, "m-ob", "t_3", "2030-06-05T18:00", 2)
        s, b = self.move([{"reference": ob["reference"]}], key="u2")
        self.assertEqual(s, 404)

    def test_mixed_restaurants_422(self):
        _, nb = book(self.tok, "m-ny", "t_ny", "2030-06-05T12:00", 2,
                     "r_ny")  # 2030-06-05 is a Wednesday
        s, b = self.move([{"reference": self.ra},
                          {"reference": nb["reference"]}], key="mx")
        self.assertEqual(s, 422)

    def test_all_or_nothing(self):
        s, b = self.move([{"reference": self.ra, "table_id": "t_3"},
                          {"reference": self.rb, "table_id": "nope"}],
                         key="ao")
        self.assertEqual(s, 404)
        s, b = req("GET", "/reservations/" + self.ra, token=self.tok)
        self.assertEqual(b["table_id"], "t_1")  # unchanged
        # key freed after failure
        s, b = self.move([{"reference": self.ra, "table_id": "t_3"}],
                         key="ao")
        self.assertEqual(s, 201)

    def test_overlap_in_batch_409(self):
        # move both onto t_1 at the same time -> collide
        s, b = self.move([{"reference": self.ra},
                          {"reference": self.rb, "table_id": "t_1",
                           "starts_at_local": "2030-06-05T18:00",
                           "party_size": 2}],
                         key="ov")
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "table_unavailable")

    def test_overlap_with_unlisted_409(self):
        s, b = self.move([{"reference": self.ra, "table_id": "t_2"}],
                         key="ou")
        self.assertEqual(s, 409)  # t_2 19:00 taken by rb; 18:00+90 overlaps

    def test_cancelled_in_batch_409(self):
        req("POST", "/reservations/%s/cancel" % self.rb, token=self.tok,
            body={})
        s, b = self.move([{"reference": self.ra, "table_id": "t_3"},
                          {"reference": self.rb, "table_id": "t_3"}],
                         key="cx")
        self.assertEqual(s, 409)
        self.assertEqual(errcode(b), "reservation_cancelled")

    def test_replay(self):
        s1, b1 = self.move([{"reference": self.ra, "table_id": "t_3"}],
                           key="rp")
        s2, b2 = self.move([{"reference": self.ra, "table_id": "t_3"}],
                           key="rp")
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(b1, b2)

    def test_no_key_400_no_auth_401(self):
        s, _ = req("POST", "/reservation-moves", token=self.tok,
                   body={"moves": [{"reference": self.ra}]})
        self.assertEqual(s, 400)
        s, _ = req("POST", "/reservation-moves", key="x",
                   body={"moves": [{"reference": self.ra}]})
        self.assertEqual(s, 401)


class ExportImport(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()

    def test_export_shape(self):
        s, b = req("GET", "/_test/export")
        self.assertEqual(s, 200)
        self.assertEqual(b["track"], "tablekeeper")
        self.assertEqual(b["format_version"], 1)
        self.assertIsInstance(b["state"], dict)

    def test_roundtrip_preserves_everything(self):
        s, b = book(self.tok, "e1")
        ref = b["reference"]
        _, exp = req("GET", "/_test/export")
        # mutate state then import restores
        reset(fixture(users=[{"id": "u_x", "email": "x@example.com",
                              "password": "correct horse",
                              "display_name": "X"}]))
        s, _ = req("GET", "/reservations", token=self.tok)
        self.assertEqual(s, 401)  # token gone after reset
        s, _ = req("POST", "/_test/import", body=exp)
        self.assertEqual(s, 204)
        # token works again, booking present
        s, b = req("GET", "/reservations/" + ref, token=self.tok)
        self.assertEqual(s, 200)
        self.assertEqual(b["reference"], ref)
        # login still works with original password
        s, b = login("ada@example.com")
        self.assertEqual(s, 200)
        # idempotent replay returns original body post-import
        s2, b2 = book(self.tok, "e1")
        self.assertEqual(s2, 200)
        self.assertEqual(b2["reference"], ref)

    def test_import_twice_no_duplication(self):
        book(self.tok, "e2")
        _, exp = req("GET", "/_test/export")
        req("POST", "/_test/import", body=exp)
        req("POST", "/_test/import", body=exp)
        s, b = req("GET", "/reservations", token=self.tok)
        self.assertEqual(len(b["reservations"]), 1)

    def test_import_bad_payloads_no_change(self):
        book(self.tok, "e3")
        for raw, expect in [("{nope", 400), ("[1]", 400)]:
            s, _ = req("POST", "/_test/import", raw=raw)
            self.assertEqual(s, expect)
        for body in [{}, {"track": "x", "format_version": 1, "state": {}},
                     {"track": "tablekeeper", "format_version": 2,
                      "state": {}},
                     {"track": "tablekeeper", "format_version": 1,
                      "state": "x"}]:
            s, b = req("POST", "/_test/import", body=body)
            self.assertEqual(s, 422, body)
            self.assertEqual(errcode(b), "validation_failed")
        # state untouched
        s, b = req("GET", "/reservations", token=self.tok)
        self.assertEqual(len(b["reservations"]), 1)

    def test_export_is_snapshot(self):
        _, exp1 = req("GET", "/_test/export")
        book(self.tok, "e4")
        _, exp2 = req("GET", "/_test/export")
        self.assertNotEqual(exp1, exp2)


class Concurrency(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = token_for()

    def test_fifty_parallel_one_wins(self):
        results = []
        lock = threading.Lock()

        def worker(i):
            s, b = book(self.tok, "race-%d" % i)
            with lock:
                results.append(s)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(409), 49)

    def test_never_5xx_under_mix(self):
        results = []
        lock = threading.Lock()

        def worker(i):
            s, _ = req("POST", "/reservations", token=self.tok,
                       key="mix-%d" % i,
                       body={"restaurant_id": "r_anker", "table_id": "t_1",
                             "starts_at_local": "2030-06-05T18:00",
                             "party_size": i % 7})
            with lock:
                results.append(s)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(s < 500 for s in results), results)


if __name__ == "__main__":
    unittest.main()
