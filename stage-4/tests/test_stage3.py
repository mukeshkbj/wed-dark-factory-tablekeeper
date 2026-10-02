"""Stage-3 HTTP contract tests: policies, terms/history and series."""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import server  # noqa: E402

BASE = None
_SERVER = None


def setUpModule():
    global BASE, _SERVER
    _SERVER = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _SERVER.daemon_threads = True
    BASE = "http://127.0.0.1:%d" % _SERVER.server_address[1]
    threading.Thread(target=_SERVER.serve_forever, daemon=True).start()


def tearDownModule():
    _SERVER.shutdown()
    _SERVER.server_close()


def req(method, path, body="skip", token=None, key=None):
    data = None if body == "skip" else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if key is not None:
        r.add_header("Idempotency-Key", key)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        payload = resp.read()
        return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, json.loads(payload) if payload else None


def fixture():
    return {
        "users": [
            {"id": "u_ada", "email": "ada@example.com",
             "password": "correct horse", "display_name": "Ada"},
            {"id": "u_bob", "email": "bob@example.com",
             "password": "correct horse", "display_name": "Bob"},
        ],
        "restaurants": [{
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
            "combinable": [["t_1", "t_2"], ["t_2", "t_3"]],
            "manager_user_ids": ["u_ada"],
        }],
        "reservations": [],
    }


def reset(fx=None):
    status, body = req("POST", "/_test/reset", body=fx or fixture())
    assert status == 204, (status, body)


def login(email="ada@example.com"):
    s, b = req("POST", "/auth/login",
               body={"email": email, "password": "correct horse"})
    assert s == 200, (s, b)
    return b["token"]


def book(token, key, table="t_2", local="2030-06-05T19:00", party=4):
    return req("POST", "/reservations", token=token, key=key, body={
        "restaurant_id": "r_anker", "table_id": table,
        "starts_at_local": local, "party_size": party})


def errcode(body):
    return body["error"]["code"]


def policy_body(effective_from="2030-06-05", **over):
    body = {
        "effective_from": effective_from,
        "slot_minutes": 15,
        "reservation_duration_minutes": 60,
        "cancellation_cutoff_minutes": 30,
        "opening_hours": [
            {"weekday": w, "opens": "18:00", "closes": "20:00"}
            for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        ],
        "capacities": {"t_1": 2, "t_2": 5, "t_3": 8},
    }
    body.update(over)
    return body


class Stage3PoliciesAndExplain(unittest.TestCase):
    def setUp(self):
        reset()
        self.manager = login("ada@example.com")
        self.diner = login("bob@example.com")

    def test_manager_ids_default_dedupe_and_reject(self):
        fx = fixture()
        fx["restaurants"][0].pop("manager_user_ids")
        s, _ = req("POST", "/_test/reset", body=fx)
        self.assertEqual(s, 204)
        s, exported = req("GET", "/_test/export")
        self.assertEqual(
            exported["state"]["restaurants"]["r_anker"]
            ["manager_user_ids"], [])

        fx["restaurants"][0]["manager_user_ids"] = [
            "u_ada", "u_ada", "u_bob"]
        s, _ = req("POST", "/_test/reset", body=fx)
        self.assertEqual(s, 204)
        s, exported = req("GET", "/_test/export")
        self.assertEqual(
            exported["state"]["restaurants"]["r_anker"]
            ["manager_user_ids"], ["u_ada", "u_bob"])

        fx["restaurants"][0]["manager_user_ids"] = ["u_ada", "u_ghost"]
        s, b = req("POST", "/_test/reset", body=fx)
        self.assertEqual((s, errcode(b)), (422, "validation_failed"))
        s, after = req("GET", "/_test/export")
        self.assertEqual(after, exported)

    def publish(self, body=None, key="policy-1", token=None):
        return req("POST", "/restaurants/r_anker/policies", token=token or self.manager,
                   key=key, body=body or policy_body())

    def test_publish_list_replay_and_selected_explain(self):
        s, b = req("GET", "/restaurants/r_anker/policies")
        self.assertEqual((s, b), (200, {"policies": []}))
        self.assertEqual(self.publish(token=self.diner)[0], 403)
        self.assertEqual(req("POST", "/restaurants/r_anker/policies",
                             token=self.manager, body=policy_body())[0], 400)
        s, published = self.publish()
        self.assertEqual(s, 201)
        self.assertEqual(published["policy_version"], 1)
        s, replay = self.publish()
        self.assertEqual((s, replay), (200, published))
        changed = policy_body(cancellation_cutoff_minutes=31)
        s, b = self.publish(body=changed)
        self.assertEqual((s, errcode(b)), (409, "idempotency_key_reuse"))
        s, b = req("GET", "/restaurants/r_anker/policies")
        self.assertEqual([p["policy_version"] for p in b["policies"]], [1])

        s, detail = req("GET", "/restaurants/r_anker")
        self.assertEqual(detail["slot_minutes"], 30)
        s, before = req("GET", "/availability?restaurant_id=r_anker"
                               "&date=2030-06-04&party_size=5&explain=true")
        self.assertEqual(s, 200)
        self.assertEqual(before["slots"][0]["explain"][0]["policy_version"], 0)
        s, after = req("GET", "/availability?restaurant_id=r_anker"
                              "&date=2030-06-05&party_size=5&explain=true")
        self.assertEqual(s, 200)
        slot = next(sl for sl in after["slots"]
                    if sl["starts_at_local"] == "2030-06-05T18:00")
        self.assertEqual(slot["available_table_ids"], ["t_2", "t_3"])
        self.assertEqual([e["table_id"] for e in slot["explain"]],
                         ["t_1", "t_2", "t_3"])
        self.assertEqual([e["policy_version"] for e in slot["explain"]],
                         [1, 1, 1])
        self.assertEqual(slot["explain"][0]["rules"], [
            {"rule": "capacity", "holds": False},
            {"rule": "no_overlap", "holds": True},
        ])
        self.assertEqual(slot["available_options"], [
            {"table_ids": ["t_2"], "capacity": 5},
            {"table_ids": ["t_3"], "capacity": 8},
            {"table_ids": ["t_1", "t_2"], "capacity": 7},
            {"table_ids": ["t_2", "t_3"], "capacity": 13},
        ])

    def test_explain_values_and_policy_validation(self):
        for suffix in ("&explain=false", "&explain=1", "&explain=",
                       "&explain=true&explain=true"):
            s, b = req("GET", "/availability?restaurant_id=r_anker"
                              "&date=2030-06-05&party_size=2" + suffix)
            self.assertEqual((s, errcode(b)), (422, "validation_failed"), suffix)
        s, b = req("GET", "/availability?restaurant_id=r_anker"
                          "&date=2030-06-05&party_size=2")
        self.assertNotIn("explain", b["slots"][0])

        for key, bad in [
                ("effective_from", "not-a-date"),
                ("slot_minutes", True),
                ("reservation_duration_minutes", 0),
                ("cancellation_cutoff_minutes", 10081),
                ("capacities", {"t_1": 2, "t_2": 5})]:
            body = policy_body()
            body[key] = bad
            s, b = self.publish(body=bad if key == "opening_hours" else body,
                                key="bad-" + key)
            self.assertEqual((s, errcode(b)), (422, "validation_failed"), key)
        body = policy_body(opening_hours=[
            {"weekday": "wed", "opens": "18:00", "closes": "20:00"},
            {"weekday": "wed", "opens": "19:00", "closes": "21:00"},
        ])
        s, b = self.publish(body=body, key="bad-hours")
        self.assertEqual((s, errcode(b)), (422, "validation_failed"))
        s, b = req("GET", "/restaurants/r_anker/policies")
        self.assertEqual(b["policies"], [])
        s, b = self.publish(key="good-after-failures")
        self.assertEqual(s, 201)
        self.assertEqual(b["policy_version"], 1)


class Stage3TermsHistoryAndMoves(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = login()
        self.other = login("bob@example.com")

    def test_terms_history_decision_and_revisioned_patch(self):
        s, created = book(self.tok, "terms-create")
        self.assertEqual(s, 201)
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["accepted_terms"]["policy_version"], 0)
        self.assertNotIn("effective_from", created["accepted_terms"])
        ref = created["reference"]

        for token in (None, self.other):
            s, b = req("GET", "/reservations/%s/history" % ref, token=token)
            self.assertEqual((s, errcode(b)), (404, "not_found"))
            s, b = req("GET", "/reservations/%s/decision" % ref, token=token)
            self.assertEqual((s, errcode(b)), (404, "not_found"))

        s, hist = req("GET", "/reservations/%s/history" % ref, token=self.tok)
        self.assertEqual(s, 200)
        self.assertEqual(len(hist["entries"]), 1)
        self.assertEqual(hist["entries"][0]["event"], "created")
        self.assertEqual(hist["entries"][0]["revision"], 1)
        self.assertEqual(hist["entries"][0]["changes"], [
            {"field": "table_id", "from": None, "to": "t_2"},
            {"field": "starts_at_local", "from": None,
             "to": "2030-06-05T19:00"},
            {"field": "party_size", "from": None, "to": 4},
        ])

        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"table_id": "t_2", "party_size": 4,
                         "starts_at_local": "2030-06-05T19:00"})
        self.assertEqual(s, 200)
        self.assertEqual(b["revision"], 1)
        s, hist2 = req("GET", "/reservations/%s/history" % ref,
                       token=self.tok)
        self.assertEqual(hist2, hist)

        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"expected_revision": 2})
        self.assertEqual((s, errcode(b)), (409, "stale_revision"))
        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"expected_revision": True})
        self.assertEqual((s, errcode(b)), (422, "validation_failed"))

        s, _pub = req("POST", "/restaurants/r_anker/policies",
                      token=self.tok, key="policy-before-patch",
                      body=policy_body(effective_from="2030-06-06"))
        self.assertEqual(s, 201)
        s, changed = req("PATCH", "/reservations/" + ref, token=self.tok,
                         body={"expected_revision": 1,
                               "starts_at_local": "2030-06-06T18:15",
                               "party_size": 3})
        self.assertEqual(s, 200)
        self.assertEqual(changed["revision"], 2)
        self.assertEqual(changed["accepted_terms"]["policy_version"], 1)
        self.assertEqual(changed["ends_at"].endswith("+02:00"), True)

        s, decision = req("GET", "/reservations/%s/decision" % ref,
                          token=self.tok)
        self.assertEqual(decision["revision"], 2)
        self.assertEqual(decision["accepted_terms"],
                         changed["accepted_terms"])
        s, hist = req("GET", "/reservations/%s/history" % ref,
                      token=self.tok)
        self.assertEqual([e["event"] for e in hist["entries"]],
                         ["created", "changed"])
        self.assertEqual([c["field"] for c in hist["entries"][1]["changes"]],
                         ["starts_at_local", "party_size"])
        self.assertEqual(hist["entries"][0]["accepted_terms"]["policy_version"], 0)
        self.assertEqual(hist["entries"][1]["accepted_terms"]["policy_version"], 1)

        s, replayed = book(self.tok, "terms-create")
        self.assertEqual((s, replayed), (200, created))
        s, cancelled = req("POST", "/reservations/%s/cancel" % ref,
                           token=self.tok, body={})
        self.assertEqual(s, 200)
        self.assertEqual(cancelled["revision"], 3)
        s, again = req("POST", "/reservations/%s/cancel" % ref,
                       token=self.tok, body={})
        self.assertEqual((s, again["revision"]), (200, 3))
        s, hist = req("GET", "/reservations/%s/history" % ref,
                      token=self.tok)
        self.assertEqual([e["event"] for e in hist["entries"]],
                         ["created", "changed", "cancelled"])
        self.assertEqual(hist["entries"][-1]["changes"], [])

    def test_pair_history_names_table_ids_and_reversed_noop(self):
        s, created = req("POST", "/reservations", token=self.tok,
                         key="pair-hist", body={
                             "restaurant_id": "r_anker",
                             "table_ids": ["t_2", "t_1"],
                             "starts_at_local": "2030-06-05T18:00",
                             "party_size": 6})
        self.assertEqual(s, 201)
        ref = created["reference"]
        s, hist = req("GET", "/reservations/%s/history" % ref,
                      token=self.tok)
        self.assertEqual(hist["entries"][0]["changes"][0], {
            "field": "table_ids", "from": None, "to": ["t_1", "t_2"]})

        s, b = req("PATCH", "/reservations/" + ref, token=self.tok,
                   body={"table_ids": ["t_2", "t_1"]})
        self.assertEqual(s, 200)
        self.assertEqual(b["revision"], 1)
        s, hist2 = req("GET", "/reservations/%s/history" % ref,
                       token=self.tok)
        self.assertEqual(hist2, hist)

        s, changed = req("PATCH", "/reservations/" + ref, token=self.tok,
                         body={"table_id": "t_3"})
        self.assertEqual(s, 200)
        self.assertEqual(changed["revision"], 2)
        s, hist = req("GET", "/reservations/%s/history" % ref,
                      token=self.tok)
        self.assertEqual(hist["entries"][1]["changes"][0], {
            "field": "table_ids", "from": ["t_1", "t_2"], "to": ["t_3"]})

    def test_moves_expected_revision_and_batch_revision(self):
        _, a = book(self.tok, "mv-a", "t_3", "2030-06-05T18:00", 2)
        _, b = book(self.tok, "mv-b", "t_3", "2030-06-05T20:00", 2)
        ra, rb = a["reference"], b["reference"]
        s, body = req("POST", "/reservation-moves", token=self.tok,
                      key="mv-stale", body={"moves": [
                          {"reference": ra, "expected_revision": 2,
                           "party_size": 3}]})
        self.assertEqual((s, errcode(body)), (409, "stale_revision"))
        s, body = req("POST", "/reservation-moves", token=self.tok,
                      key="mv-ok", body={"moves": [
                          {"reference": ra, "expected_revision": 1,
                           "party_size": 3},
                          {"reference": rb, "expected_revision": 1,
                           "party_size": 4}]})
        self.assertEqual(s, 201)
        self.assertEqual([r["revision"] for r in body["reservations"]],
                         [2, 2])
        s, noop = req("POST", "/reservation-moves", token=self.tok,
                      key="mv-noop", body={"moves": [
                          {"reference": ra, "party_size": 3}]})
        self.assertEqual(s, 201)
        self.assertEqual(noop["reservations"][0]["revision"], 2)
        s, exp = req("GET", "/_test/export")
        self.assertEqual(exp["state"]["restaurant_revisions"]["r_anker"], 3)


class Stage3Series(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = login()
        self.other = login("bob@example.com")

    def test_series_lifecycle_replay_and_private_get(self):
        s, anchor = book(self.tok, "series-anchor")
        self.assertEqual(s, 201)
        ref = anchor["reference"]
        body = {"anchor_reference": ref, "count": 3, "interval_weeks": 1}
        s, created = req("POST", "/series", token=self.tok,
                         key="series-create", body=body)
        self.assertEqual(s, 201)
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["interval_weeks"], 1)
        self.assertEqual(len(created["occurrences"]), 3)
        self.assertEqual(created["occurrences"][0]["reference"], ref)
        self.assertFalse(created["occurrences"][0]["exception"])
        refs = [o["reference"] for o in created["occurrences"]]
        self.assertEqual(len(set(refs)), 3)
        self.assertEqual(created["occurrences"][1]["reservation"]
                         ["starts_at_local"], "2030-06-12T19:00")

        for token in (None, self.other):
            s, b = req("GET", "/series/" + created["series_id"], token=token)
            self.assertEqual((s, errcode(b)), (404, "not_found"))
        s, current = req("GET", "/series/" + created["series_id"],
                         token=self.tok)
        self.assertEqual(current["revision"], 1)

        second_ref = refs[1]
        s, patched = req("PATCH", "/reservations/" + second_ref,
                         token=self.tok,
                         body={"party_size": 3, "expected_revision": 1})
        self.assertEqual(s, 200)
        self.assertEqual(patched["revision"], 2)
        s, current = req("GET", "/series/" + created["series_id"],
                         token=self.tok)
        self.assertEqual(current["revision"], 2)
        self.assertTrue(current["occurrences"][1]["exception"])

        third_ref = refs[2]
        s, cancelled = req("POST", "/reservations/%s/cancel" % third_ref,
                           token=self.tok, body={})
        self.assertEqual(s, 200)
        self.assertEqual(cancelled["revision"], 2)
        s, current = req("GET", "/series/" + created["series_id"],
                         token=self.tok)
        self.assertEqual(current["revision"], 3)
        self.assertFalse(current["occurrences"][2]["exception"])
        s, anchor_view = req("GET", "/reservations/" + ref, token=self.tok)
        self.assertEqual(anchor_view["status"], "confirmed")

        s, replay = req("POST", "/series", token=self.tok,
                        key="series-create", body=dict(body))
        self.assertEqual(s, 200)
        self.assertEqual(replay, created)

        s, b = req("POST", "/series", token=self.tok, key="series-again",
                   body=body)
        self.assertEqual((s, errcode(b)), (409, "already_in_series"))

    def test_series_failure_is_atomic_and_key_is_reusable(self):
        s, anchor = book(self.tok, "series-anchor")
        ref = anchor["reference"]
        _, blocker = book(self.tok, "series-blocker", "t_2",
                          "2030-06-12T19:00", 2)
        body = {"anchor_reference": ref, "count": 3, "interval_weeks": 1}
        s, b = req("POST", "/series", token=self.tok, key="series-fail",
                   body=body)
        self.assertEqual((s, errcode(b)), (409, "table_unavailable"))
        s, exported = req("GET", "/_test/export")
        self.assertNotIn(
            "series-fail",
            exported["state"]["idempotency"].get("u_ada", {}))
        s, mine = req("GET", "/reservations", token=self.tok)
        self.assertEqual(len(mine["reservations"]), 2)
        s, b = req("GET", "/series/ser_1", token=self.tok)
        self.assertEqual(s, 404)

        req("POST", "/reservations/%s/cancel" % blocker["reference"],
            token=self.tok, body={})
        s, created = req("POST", "/series", token=self.tok,
                         key="series-fail", body=body)
        self.assertEqual(s, 201)
        self.assertEqual(len(created["occurrences"]), 3)


class Stage3Upgrade(unittest.TestCase):
    def setUp(self):
        reset()
        self.tok = login()

    def test_stage3_export_import_roundtrips_policy_series_history(self):
        s, _ = req("POST", "/restaurants/r_anker/policies", token=self.tok,
                   key="policy-export", body=policy_body())
        self.assertEqual(s, 201)
        s, anchor = book(self.tok, "export-anchor")
        ref = anchor["reference"]
        s, ser = req("POST", "/series", token=self.tok, key="series-export",
                     body={"anchor_reference": ref, "count": 2,
                           "interval_weeks": 1})
        self.assertEqual(s, 201)
        second_ref = ser["occurrences"][1]["reference"]
        s, _ = req("PATCH", "/reservations/" + second_ref, token=self.tok,
                   body={"party_size": 3})
        self.assertEqual(s, 200)
        s, exported = req("GET", "/_test/export")
        self.assertEqual(s, 200)

        reset(fixture())
        s, _ = req("POST", "/_test/import", body=exported)
        self.assertEqual(s, 204)
        s, current = req("GET", "/series/" + ser["series_id"], token=self.tok)
        self.assertEqual(s, 200)
        self.assertEqual(current["revision"], 2)
        self.assertTrue(current["occurrences"][1]["exception"])
        s, hist = req("GET", "/reservations/%s/history" % second_ref,
                      token=self.tok)
        self.assertEqual([e["event"] for e in hist["entries"]],
                         ["created", "changed"])
        s, replay = req("POST", "/series", token=self.tok,
                        key="series-export",
                        body={"anchor_reference": ref, "count": 2,
                              "interval_weeks": 1})
        self.assertEqual((s, replay), (200, ser))

    def test_stage2_import_normalises_stage3_fields_and_adopts(self):
        s, old = book(self.tok, "old-create")
        ref = old["reference"]
        s, exp = req("GET", "/_test/export")
        for res in exp["state"]["reservations"].values():
            res.pop("revision", None)
            res.pop("accepted_terms", None)
            res.pop("history", None)
        exp["state"].pop("policies", None)
        exp["state"].pop("series", None)
        exp["state"].pop("restaurant_revisions", None)
        exp["state"]["counters"].pop("series", None)
        reset(fixture())
        s, _ = req("POST", "/_test/import", body=exp)
        self.assertEqual(s, 204)
        s, decision = req("GET", "/reservations/%s/decision" % ref,
                          token=self.tok)
        self.assertEqual(decision["revision"], 1)
        self.assertEqual(decision["accepted_terms"]["policy_version"], 0)
        s, hist = req("GET", "/reservations/%s/history" % ref,
                      token=self.tok)
        self.assertEqual(len(hist["entries"]), 1)
        s, ser = req("POST", "/series", token=self.tok, key="adopt-old",
                     body={"anchor_reference": ref, "count": 2,
                           "interval_weeks": 1})
        self.assertEqual(s, 201)


if __name__ == "__main__":
    unittest.main()
