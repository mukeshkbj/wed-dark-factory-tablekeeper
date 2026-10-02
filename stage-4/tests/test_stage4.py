"""Stage-4 HTTP tests: closure replans and recurring-series amendments."""

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
    if key:
        r.add_header("Idempotency-Key", key)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        payload = resp.read()
        return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def fixture():
    return {
        "users": [
            {"id": "u_mgr", "email": "mgr@example.com",
             "password": "correct horse", "display_name": "Manager"},
            {"id": "u_diner", "email": "diner@example.com",
             "password": "correct horse", "display_name": "Diner"},
        ],
        "restaurants": [{
            "id": "r_anker", "name": "Zum Anker",
            "timezone": "UTC",
            "slot_minutes": 30, "reservation_duration_minutes": 60,
            "cancellation_cutoff_minutes": 0,
            "opening_hours": [
                {"weekday": w, "opens": "17:00", "closes": "23:00"}
                for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            ],
            "tables": [
                {"id": "t_1", "label": "one", "capacity": 2},
                {"id": "t_2", "label": "two", "capacity": 4},
                {"id": "t_3", "label": "three", "capacity": 4},
            ],
            "combinable": [["t_1", "t_3"]],
            "manager_user_ids": ["u_mgr"],
        }],
        "reservations": [],
    }


def reset(fx=None):
    status, body = req("POST", "/_test/reset", body=fx or fixture())
    assert status == 204, (status, body)


def login(email):
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


def export():
    s, body = req("GET", "/_test/export")
    assert s == 200
    return body


class Stage4Replans(unittest.TestCase):
    def setUp(self):
        reset()
        self.manager = login("mgr@example.com")
        self.diner = login("diner@example.com")

    def closure(self, table="t_2"):
        return {"table_id": table,
                "from": "2030-06-05T19:30:00+00:00",
                "to": "2030-06-05T20:30:00+00:00"}

    def preview(self, body=None, key="plan-1", token=None):
        return req("POST", "/restaurants/r_anker/replans", token=token or self.manager,
                   key=key, body=body or self.closure())

    def test_preview_apply_closure_history_and_replays(self):
        s, reservation = book(self.diner, "book-1")
        self.assertEqual(s, 201)
        s, preview = self.preview()
        self.assertEqual(s, 201)
        self.assertEqual(preview["restaurant_revision"], 1)
        self.assertEqual(preview["closure"], self.closure())
        self.assertEqual(preview["assignments"], [{
            "reference": reservation["reference"],
            "table_ids": ["t_3"], "changed": True}])
        self.assertEqual(preview["moved_count"], 1)
        self.assertEqual(preview["unused_seats"], 0)
        self.assertEqual(export()["state"]["closures"], {})

        apply_path = ("/restaurants/r_anker/replans/%s/apply"
                      % preview["plan_id"])
        s, applied = req("POST", apply_path, token=self.manager,
                         key="apply-1", body={})
        self.assertEqual(s, 201)
        self.assertEqual(applied["restaurant_revision"], 2)
        self.assertEqual(applied["reservations"][0]["table_ids"], ["t_3"])
        self.assertEqual(applied["reservations"][0]["revision"], 2)

        s, history = req("GET", "/reservations/%s/history"
                         % reservation["reference"], token=self.diner)
        self.assertEqual(history["entries"][-1]["event"], "reassigned")
        self.assertEqual(history["entries"][-1]["plan_id"],
                         preview["plan_id"])
        self.assertEqual(history["entries"][-1]["changes"], [{
            "field": "table_ids", "from": ["t_2"], "to": ["t_3"]}])

        s, availability = req(
            "GET", "/availability?restaurant_id=r_anker&date=2030-06-05"
                   "&party_size=4&explain=true")
        slot = next(item for item in availability["slots"]
                    if item["starts_at_local"] == "2030-06-05T19:00")
        explain = {e["table_id"]: e for e in slot["explain"]}
        self.assertFalse(explain["t_2"]["rules"][1]["holds"])
        s, conflict = book(self.diner, "closed-table", table="t_2",
                           local="2030-06-05T19:00")
        self.assertEqual((s, errcode(conflict)), (409, "table_unavailable"))

        s, replay = req("POST", apply_path, token=self.manager,
                        key="apply-1", body={})
        self.assertEqual((s, replay), (200, applied))
        s, different_key = req("POST", apply_path, token=self.manager,
                               key="apply-2", body={})
        self.assertEqual((s, errcode(different_key)),
                         (409, "plan_already_applied"))
        s, original = self.preview()
        self.assertEqual((s, original), (200, preview))

    def test_stale_no_feasible_and_validation(self):
        s, reservation = book(self.diner, "book-stale")
        self.assertEqual(s, 201)
        s, preview = self.preview(key="plan-stale")
        self.assertEqual(s, 201)
        s, _ = req("POST", "/reservations/%s/cancel"
                   % reservation["reference"], token=self.diner, body={})
        self.assertEqual(s, 200)
        s, stale = req("POST", "/restaurants/r_anker/replans/%s/apply"
                       % preview["plan_id"], token=self.manager,
                       key="apply-stale", body={})
        self.assertEqual((s, errcode(stale)), (409, "stale_plan"))

        reset()
        self.manager = login("mgr@example.com")
        self.diner = login("diner@example.com")
        book(self.diner, "book-a", "t_2", party=4)
        s, blocker = book(self.diner, "book-b", "t_3", party=4)
        self.assertEqual(s, 201)
        s, failed = self.preview(key="plan-none")
        self.assertEqual((s, errcode(failed)), (409, "no_feasible_plan"))
        self.assertNotIn("plan-none",
                         export()["state"]["idempotency"].get("u_mgr", {}))
        s, _ = req("POST", "/reservations/%s/cancel" % blocker["reference"],
                   token=self.diner, body={})
        s, retried = self.preview(key="plan-none")
        self.assertEqual(s, 201)

        for body in ({"table_id": "t_2", "from": "bad",
                      "to": "2030-06-05T20:30:00+00:00"},
                     {"table_id": "t_2",
                      "from": "2030-06-05T20:30:00+00:00",
                      "to": "2030-06-05T19:30:00+00:00"},
                     {"table_id": "t_2",
                      "from": "2030-06-05T19:30:00+00:00",
                      "to": "2030-06-05T19:30:00+00:00"}):
            s, b = self.preview(body=body, key=json.dumps(body))
            self.assertEqual((s, errcode(b)), (422, "validation_failed"))
        s, b = self.preview(body=self.closure("t_missing"),
                            key="unknown-table")
        self.assertEqual((s, errcode(b)), (404, "not_found"))
        s, b = self.preview(token=self.diner, key="not-manager")
        self.assertEqual((s, errcode(b)), (403, "forbidden"))

    def test_half_open_boundary_and_previous_closure(self):
        s, _ = book(self.diner, "touching-end", local="2030-06-05T18:30")
        self.assertEqual(s, 201)
        s, empty = self.preview(key="boundary-plan")
        self.assertEqual(s, 201)
        self.assertEqual(empty["assignments"], [])
        s, applied = req(
            "POST", "/restaurants/r_anker/replans/%s/apply"
            % empty["plan_id"], token=self.manager,
            key="boundary-apply", body={})
        self.assertEqual(s, 201)

        s, moving = book(self.diner, "previous-closure", table="t_1",
                         party=2)
        self.assertEqual(s, 201)
        body = {"table_id": "t_1",
                "from": "2030-06-05T19:45:00+00:00",
                "to": "2030-06-05T20:45:00+00:00"}
        s, preview = self.preview(body=body, key="second-plan")
        self.assertEqual(s, 201)
        self.assertEqual(preview["assignments"], [{
            "reference": moving["reference"],
            "table_ids": ["t_3"], "changed": True}])

    def test_optimization_and_planning_limit(self):
        s, reservation = book(self.diner, "book-small", party=2)
        self.assertEqual(s, 201)
        s, preview = self.preview(key="plan-opt")
        self.assertEqual(s, 201)
        self.assertEqual(preview["assignments"][0]["table_ids"], ["t_1"])
        self.assertEqual(preview["unused_seats"], 0)

        fx = fixture()
        for number in range(4, 8):
            fx["restaurants"][0]["tables"].append({
                "id": "t_%d" % number, "label": str(number),
                "capacity": 2})
        reset(fx)
        self.manager = login("mgr@example.com")
        s, b = self.preview(key="too-many-tables")
        self.assertEqual((s, errcode(b)), (422, "planning_limit"))

    def test_pending_plan_survives_export_import(self):
        s, _ = book(self.diner, "book-import")
        self.assertEqual(s, 201)
        s, preview = self.preview(key="plan-import")
        self.assertEqual(s, 201)
        snapshot = export()
        reset()
        s, _ = req("POST", "/_test/import", body=snapshot)
        self.assertEqual(s, 204)
        s, applied = req(
            "POST", "/restaurants/r_anker/replans/%s/apply"
            % preview["plan_id"], token=self.manager,
            key="apply-import", body={})
        self.assertEqual(s, 201)
        self.assertEqual(applied["restaurant_revision"], 2)

    def test_invalid_applied_plan_import_is_atomic(self):
        s, _ = book(self.diner, "book-bad-import")
        self.assertEqual(s, 201)
        s, preview = self.preview(key="plan-bad-import")
        self.assertEqual(s, 201)
        s, _ = req("POST", "/restaurants/r_anker/replans/%s/apply"
                   % preview["plan_id"], token=self.manager,
                   key="apply-bad-import", body={})
        self.assertEqual(s, 201)
        snapshot = export()
        valid_after = export()
        snapshot["state"]["plans"][preview["plan_id"]]["status"] = "pending"
        s, rejected = req("POST", "/_test/import", body=snapshot)
        self.assertEqual((s, errcode(rejected)),
                         (422, "validation_failed"))
        self.assertEqual(export(), valid_after)


class Stage4SeriesAmend(unittest.TestCase):
    def setUp(self):
        reset()
        self.manager = login("mgr@example.com")
        self.diner = login("diner@example.com")

    def make_series(self, table="t_2", count=3):
        s, anchor = book(self.diner, "series-anchor", table=table)
        self.assertEqual(s, 201)
        s, ser = req("POST", "/series", token=self.diner,
                     key="series-create",
                     body={"anchor_reference": anchor["reference"],
                           "count": count, "interval_weeks": 1})
        self.assertEqual(s, 201)
        return ser

    def amend(self, series_id, expected, key="series-amend",
              from_index=0, local_time="20:30"):
        return req("POST", "/series/%s/amend" % series_id,
                   token=self.diner, key=key,
                   body={"expected_revision": expected,
                         "from_index": from_index,
                         "local_time": local_time})

    def test_amend_revision_noop_and_exception_exclusion(self):
        ser = self.make_series()
        self.assertEqual(self.amend(ser["series_id"], 99)[1]["error"]["code"],
                         "stale_revision")
        s, amended = self.amend(ser["series_id"], 1, from_index=1)
        self.assertEqual(s, 201)
        self.assertEqual(amended["revision"], 2)
        self.assertEqual(
            [o["reservation"]["starts_at_local"][11:]
             for o in amended["occurrences"]],
            ["19:00", "20:30", "20:30"])
        self.assertEqual(amended["occurrences"][1]["reservation"]["revision"], 2)
        self.assertFalse(any(o["exception"] for o in amended["occurrences"]))
        s, exported = req("GET", "/_test/export")
        self.assertEqual(
            exported["state"]["restaurant_revisions"]["r_anker"], 3)

        s, noop = self.amend(ser["series_id"], 2, key="series-noop",
                             from_index=0, local_time="19:00")
        # Index 0 is already at 19:00; indices 1..2 are skipped only by
        # from_index semantics, so this is a partial no-op failure-free read.
        self.assertEqual(s, 201)
        self.assertEqual(noop["revision"], 3)

        second = amended["occurrences"][1]["reservation"]
        s, _ = req("PATCH", "/reservations/%s" % second["reference"],
                   token=self.diner, body={"party_size": 3})
        self.assertEqual(s, 200)
        s, current = req("GET", "/series/%s" % ser["series_id"],
                         token=self.diner)
        self.assertTrue(current["occurrences"][1]["exception"])
        s, after = self.amend(ser["series_id"], current["revision"],
                              key="series-exception", from_index=0,
                              local_time="21:00")
        self.assertEqual(s, 201)
        self.assertEqual(
            after["occurrences"][1]["reservation"]["starts_at_local"],
            "2030-06-12T19:00")

    def test_amend_failure_is_atomic_and_key_reusable(self):
        s, blocker = book(self.diner, "blocker", table="t_3",
                          local="2030-06-05T20:30", party=4)
        self.assertEqual(s, 201)
        ser = self.make_series(table="t_3", count=2)
        s, failed = self.amend(ser["series_id"], 1)
        self.assertEqual((s, errcode(failed)), (409, "table_unavailable"))
        s, current = req("GET", "/series/%s" % ser["series_id"],
                         token=self.diner)
        self.assertEqual(current["revision"], 1)
        self.assertEqual(
            current["occurrences"][0]["reservation"]["revision"], 1)
        self.assertNotIn(
            "series-amend",
            export()["state"]["idempotency"].get("u_diner", {}))

        req("POST", "/reservations/%s/cancel" % blocker["reference"],
            token=self.diner, body={})
        s, retried = self.amend(ser["series_id"], 1)
        self.assertEqual(s, 201)
        self.assertEqual(retried["revision"], 2)

    def test_repair_moves_series_occurrence_without_exception(self):
        ser = self.make_series(count=2)
        second = ser["occurrences"][1]["reservation"]
        s, _ = req("PATCH", "/reservations/%s" % second["reference"],
                   token=self.diner, body={"party_size": 3})
        self.assertEqual(s, 200)
        s, current = req("GET", "/series/%s" % ser["series_id"],
                         token=self.diner)
        self.assertEqual(current["revision"], 2)
        self.assertTrue(current["occurrences"][1]["exception"])

        body = {"table_id": "t_2",
                "from": "2030-06-05T18:00:00+00:00",
                "to": "2030-06-05T20:00:00+00:00"}
        s, preview = req("POST", "/restaurants/r_anker/replans",
                         token=self.manager, key="series-plan", body=body)
        self.assertEqual(s, 201)
        s, applied = req("POST", "/restaurants/r_anker/replans/%s/apply"
                         % preview["plan_id"], token=self.manager,
                         key="series-apply", body={})
        self.assertEqual(s, 201)
        s, current = req("GET", "/series/%s" % ser["series_id"],
                         token=self.diner)
        self.assertEqual(current["revision"], 3)
        self.assertTrue(current["occurrences"][1]["exception"])
        self.assertEqual(
            current["occurrences"][0]["reservation"]["table_ids"], ["t_3"])

    def test_stage3_export_import_series_amend(self):
        ser = self.make_series(count=2)
        snapshot = export()
        snapshot["state"].pop("plans", None)
        snapshot["state"].pop("closures", None)
        snapshot["state"]["counters"].pop("plan", None)
        reset()
        s, _ = req("POST", "/_test/import", body=snapshot)
        self.assertEqual(s, 204)
        s, amended = self.amend(ser["series_id"], 1, from_index=1)
        self.assertEqual(s, 201)
        self.assertEqual(amended["revision"], 2)


if __name__ == "__main__":
    unittest.main()
