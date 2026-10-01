"""Spec-derived unit tests for stage-1/src/fixtures.py (spec section 4,
coordinator rulings R-1/R-3/G-5: reset-side failures -> 422
validation_failed).

Run from anywhere:
    python stage-1/tests/test_fixtures.py
"""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import fixtures  # noqa: E402


def _user(**over):
    u = {"id": "u_1", "email": "ada@example.com",
         "password": "correct horse", "display_name": "Ada"}
    u.update(over)
    return u


def _restaurant(**over):
    r = {"id": "r_1", "name": "Zum Anker", "timezone": "Europe/Berlin",
         "slot_minutes": 30, "reservation_duration_minutes": 90,
         "cancellation_cutoff_minutes": 120,
         "opening_hours": [
             {"weekday": "thu", "opens": "18:00", "closes": "23:00"}],
         "tables": [{"id": "t_1", "label": "1", "capacity": 4}]}
    r.update(over)
    return r


def _fixture(**over):
    f = {"users": [_user()], "restaurants": [_restaurant()],
         "reservations": []}
    f.update(over)
    return f


class AcceptValid(unittest.TestCase):
    def test_minimal_fixture(self):
        out = fixtures.validate_fixture(_fixture())
        self.assertEqual(out["restaurants"][0]["id"], "r_1")

    def test_returns_a_copy(self):
        f = _fixture()
        out = fixtures.validate_fixture(f)
        out["restaurants"][0]["name"] = "mutated"
        self.assertEqual(f["restaurants"][0]["name"], "Zum Anker")

    def test_empty_sections_ok(self):
        out = fixtures.validate_fixture(
            {"users": [], "restaurants": [], "reservations": []})
        self.assertEqual(out["reservations"], [])

    def test_demo_seed_validates(self):
        out = fixtures.validate_fixture(fixtures.demo_seed())
        self.assertEqual(len(out["restaurants"]), 3)
        self.assertEqual(len(out["reservations"]), 4)
        demo = [u for u in out["users"]
                if u["email"] == "demo@tablekeeper.test"]
        self.assertEqual(demo[0]["password"], "demo-pass-123")
        for res in out["reservations"]:
            self.assertEqual(res["status"], "confirmed")

    def test_seeded_reservation_full_shape(self):
        f = _fixture(reservations=[{
            "id": "res_1", "reference": "K3P7QW", "user_id": "u_1",
            "restaurant_id": "r_1", "table_id": "t_1", "party_size": 2,
            "starts_at_local": "2026-10-01T19:00", "status": "confirmed"}])
        self.assertEqual(fixtures.validate_fixture(f)["reservations"][0]
                         ["reference"], "K3P7QW")


class Rejections(unittest.TestCase):
    def assertFails(self, body):
        with self.assertRaises(fixtures.FixtureError) as ctx:
            fixtures.validate_fixture(body)
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "validation_failed")
        return ctx.exception

    def test_non_dict_body(self):
        for body in ([], "x", 4, None, True):
            self.assertFails(body)

    def test_sections_must_be_arrays(self):
        self.assertFails(_fixture(users={}))
        self.assertFails(_fixture(restaurants="no"))
        self.assertFails(_fixture(reservations=None))

    def test_id_rules(self):
        self.assertFails(_fixture(users=[_user(id="x" * 65)]))
        self.assertFails(_fixture(users=[_user(id=123)]))
        self.assertFails(_fixture(restaurants=[_restaurant(id=None)]))
        self.assertFails(_fixture(
            restaurants=[_restaurant(tables=[
                {"id": "t" * 65, "label": "x", "capacity": 2}])]))

    def test_user_fields(self):
        self.assertFails(_fixture(users=[_user(email="no-at-sign")]))
        self.assertFails(_fixture(users=[_user(email="@no-local")]))
        self.assertFails(_fixture(users=[_user(email="trailing@")]))
        self.assertFails(_fixture(users=[_user(password=42)]))
        self.assertFails(_fixture(users=[_user(display_name=1)]))
        self.assertFails(_fixture(
            users=[_user(), _user(id="u_2", email="ADA@example.com")]))

    def test_restaurant_fields(self):
        self.assertFails(_fixture(
            restaurants=[_restaurant(timezone="Mars/Olympus")]))
        self.assertFails(_fixture(
            restaurants=[_restaurant(timezone=12)]))
        for key in ("slot_minutes", "reservation_duration_minutes",
                    "cancellation_cutoff_minutes"):
            self.assertFails(_fixture(restaurants=[_restaurant(**{key: 0})]))
            self.assertFails(_fixture(
                restaurants=[_restaurant(**{key: True})]))
            self.assertFails(_fixture(
                restaurants=[_restaurant(**{key: "30"})]))
        self.assertFails(_fixture(
            restaurants=[_restaurant(slot_minutes=-5)]))

    def test_opening_hours(self):
        oh = [{"weekday": "noday", "opens": "18:00", "closes": "23:00"}]
        self.assertFails(_fixture(restaurants=[_restaurant(opening_hours=oh)]))
        for bad_time in ("9:00", "18:0", "18-00", "24:00", "18:60", 18):
            oh = [{"weekday": "thu", "opens": bad_time, "closes": "23:00"}]
            self.assertFails(
                _fixture(restaurants=[_restaurant(opening_hours=oh)]))
        oh = [{"weekday": "thu", "opens": "18:00", "closes": "18:00"}]
        self.assertFails(_fixture(restaurants=[_restaurant(opening_hours=oh)]))
        oh = [{"weekday": "thu", "opens": "23:00", "closes": "18:00"}]
        self.assertFails(_fixture(restaurants=[_restaurant(opening_hours=oh)]))
        self.assertFails(_fixture(
            restaurants=[_restaurant(opening_hours="thu 18-23")]))

    def test_table_fields(self):
        self.assertFails(_fixture(restaurants=[_restaurant(
            tables=[{"id": "t_1", "label": "1", "capacity": 0}])]))
        self.assertFails(_fixture(restaurants=[_restaurant(
            tables=[{"id": "t_1", "label": "1", "capacity": "4"}])]))
        self.assertFails(_fixture(restaurants=[_restaurant(
            tables=[{"id": "t_1", "label": "1", "capacity": True}])]))
        self.assertFails(_fixture(restaurants=[_restaurant(
            tables=[{"id": "t_1", "capacity": 4}])]))  # no label
        self.assertFails(_fixture(restaurants=[_restaurant(tables={})]))

    def test_reservation_fields(self):
        base = {"id": "res_1", "reference": "K3P7QW", "user_id": "u_1",
                "restaurant_id": "r_1", "table_id": "t_1", "party_size": 2,
                "starts_at_local": "2026-10-01T19:00", "status": "confirmed"}

        def res(**over):
            r = dict(base)
            r.update(over)
            return _fixture(reservations=[r])

        self.assertFails(res(reference="k3p7qw"))          # lowercase
        self.assertFails(res(reference="SHORT"))           # < 6 chars
        self.assertFails(res(reference="TOOLONGABCDEFGH")) # > 12 chars
        self.assertFails(res(user_id="u_ghost"))
        self.assertFails(res(restaurant_id="r_ghost"))
        self.assertFails(res(table_id="t_ghost"))
        self.assertFails(res(party_size=0))
        self.assertFails(res(party_size="4"))
        self.assertFails(res(starts_at_local=12345))
        self.assertFails(res(starts_at_local="2026-10-01T19:00+02:00"))
        self.assertFails(res(starts_at_local="2026-03-29T02:30"))  # gap
        self.assertFails(res(status="maybe"))
        self.assertFails(res(id="x" * 65))
        # duplicate ids / references
        f = _fixture(reservations=[base, dict(base, id="res_2")])
        self.assertFails(f)
        f = _fixture(reservations=[base, dict(base, reference="OTHER99")])
        self.assertFails(f)


if __name__ == "__main__":
    unittest.main()
