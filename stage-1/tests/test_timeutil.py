"""Spec-derived unit tests for stage-1/src/timeutil.py (spec section 9).

Run from anywhere:
    python stage-1/tests/test_timeutil.py
    python -m unittest stage-1.tests.test_timeutil   (if importable)
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import timeutil  # noqa: E402

BERLIN = "Europe/Berlin"
NYC = "America/New_York"


def _rest(**over):
    rest = {
        "id": "r_test",
        "name": "Test",
        "timezone": BERLIN,
        "slot_minutes": 30,
        "reservation_duration_minutes": 90,
        "cancellation_cutoff_minutes": 120,
        "opening_hours": [
            {"weekday": w, "opens": "18:00", "closes": "23:00"}
            for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        ],
        "tables": [],
    }
    rest.update(over)
    return rest


class ResolveLocal(unittest.TestCase):
    def test_plain_local_resolves_in_zone(self):
        dt = timeutil.resolve_local(BERLIN, "2026-09-24T19:00")
        self.assertEqual(dt.utcoffset(), timedelta(hours=2))  # CEST
        self.assertEqual((dt.hour, dt.minute), (19, 0))

    def test_winter_berlin_offset(self):
        dt = timeutil.resolve_local(BERLIN, "2026-01-15T19:00")
        self.assertEqual(dt.utcoffset(), timedelta(hours=1))  # CET

    def test_malformed_inputs(self):
        bad = [
            "2026-09-24T19:00:00",       # seconds
            "2026-09-24T19:00+02:00",    # offset suffix
            "2026-09-24T19:00Z",         # Z suffix
            "2026-09-24 19:00",          # space separator
            "2026-9-24T19:00",           # single-digit month
            "2026-09-24T7:00",           # single-digit hour
            "19:00", "2026-09-24", "", "banana",
            202609241900, None, ["2026-09-24T19:00"],
        ]
        for value in bad:
            with self.assertRaises(timeutil.MalformedLocalTime, msg=value):
                timeutil.resolve_local(BERLIN, value)

    def test_invalid_calendar_values_are_malformed(self):
        for value in ("2026-13-24T19:00", "2026-02-30T19:00",
                      "2026-09-24T25:00", "2026-09-24T19:60"):
            with self.assertRaises(timeutil.MalformedLocalTime, msg=value):
                timeutil.resolve_local(BERLIN, value)

    def test_spring_forward_gap_berlin(self):
        # 2026-03-29: clocks jump 02:00 -> 03:00; the hour never exists.
        for local in ("2026-03-29T02:00", "2026-03-29T02:30",
                      "2026-03-29T02:59"):
            with self.assertRaises(timeutil.InvalidLocalTime, msg=local):
                timeutil.resolve_local(BERLIN, local)
        # Edges of the gap do exist.
        self.assertEqual(
            timeutil.resolve_local(BERLIN, "2026-03-29T01:59").utcoffset(),
            timedelta(hours=1))
        self.assertEqual(
            timeutil.resolve_local(BERLIN, "2026-03-29T03:00").utcoffset(),
            timedelta(hours=2))

    def test_spring_forward_gap_new_york(self):
        # 2026-03-08: clocks jump 02:00 -> 03:00.
        with self.assertRaises(timeutil.InvalidLocalTime):
            timeutil.resolve_local(NYC, "2026-03-08T02:30")
        self.assertEqual(
            timeutil.resolve_local(NYC, "2026-03-08T01:59").utcoffset(),
            timedelta(hours=-5))
        self.assertEqual(
            timeutil.resolve_local(NYC, "2026-03-08T03:00").utcoffset(),
            timedelta(hours=-4))

    def test_fall_back_first_occurrence_berlin(self):
        # 2026-10-25: 03:00 -> 02:00, so 02:30 occurs twice; the spec
        # resolves to the FIRST occurrence (still CEST, +02:00).
        dt = timeutil.resolve_local(BERLIN, "2026-10-25T02:30")
        self.assertEqual(dt.utcoffset(), timedelta(hours=2))
        self.assertEqual(dt.fold, 0)

    def test_fall_back_first_occurrence_new_york(self):
        # 2026-11-01: 02:00 -> 01:00; first 01:30 is still EDT (-04:00).
        dt = timeutil.resolve_local(NYC, "2026-11-01T01:30")
        self.assertEqual(dt.utcoffset(), timedelta(hours=-4))
        self.assertEqual(dt.fold, 0)


class SlotsForDay(unittest.TestCase):
    def test_grid_and_closes_boundary(self):
        # 18:00-23:00, step 30, duration 90 -> last legal start is 21:30
        # (21:30 + 90 == 23:00 is included); 22:00 must NOT appear.
        slots = timeutil.slots_for_day(_rest(), "2026-10-01")  # thu
        locals_ = [s["starts_at_local"] for s in slots]
        self.assertEqual(locals_[0], "2026-10-01T18:00")
        self.assertEqual(locals_[-1], "2026-10-01T21:30")
        self.assertNotIn("2026-10-01T22:00", locals_)
        self.assertEqual(len(slots), 8)  # 18:00 .. 21:30 every 30 min

    def test_entry_shape(self):
        slot = timeutil.slots_for_day(_rest(), "2026-10-01")[0]
        self.assertEqual(slot["starts_at_local"], "2026-10-01T18:00")
        self.assertEqual(slot["starts_at"], "2026-10-01T18:00:00+02:00")
        # aware-datetime views of the same instants
        self.assertIsInstance(slot["start_instant"], datetime)
        self.assertIsInstance(slot["end_instant"], datetime)
        self.assertIsInstance(slot["ends_at"], datetime)
        self.assertEqual(slot["end_instant"],
                         slot["start_instant"] + timedelta(minutes=90))
        self.assertEqual(slot["ends_at_rfc3339"],
                         "2026-10-01T19:30:00+02:00")

    def test_closed_weekday_empty(self):
        rest = _rest(opening_hours=[
            {"weekday": "fri", "opens": "18:00", "closes": "23:00"}])
        self.assertEqual(timeutil.slots_for_day(rest, "2026-10-01"), [])
        self.assertEqual(len(timeutil.slots_for_day(rest, "2026-10-02")), 8)

    def test_spring_forward_skips_gap_slots(self):
        # Berlin 2026-03-29 (sun): the 02:00 hour never exists.
        rest = _rest(opening_hours=[
            {"weekday": "sun", "opens": "00:00", "closes": "06:00"}],
            slot_minutes=30, reservation_duration_minutes=30)
        locals_ = [s["starts_at_local"]
                   for s in timeutil.slots_for_day(rest, "2026-03-29")]
        self.assertIn("2026-03-29T01:30", locals_)
        self.assertIn("2026-03-29T03:00", locals_)
        for missing in ("2026-03-29T02:00", "2026-03-29T02:30"):
            self.assertNotIn(missing, locals_)

    def test_fall_back_ambiguous_once_and_absolute_duration(self):
        # Berlin 2026-10-25 (sun): 02:00-02:59 occurs twice; each local
        # appears exactly once, resolved to the first occurrence (+02:00).
        # Duration is absolute: 90 min from 01:30 ends at local 02:00.
        rest = _rest(opening_hours=[
            {"weekday": "sun", "opens": "00:00", "closes": "05:00"}],
            slot_minutes=30, reservation_duration_minutes=90)
        slots = timeutil.slots_for_day(rest, "2026-10-25")
        locals_ = [s["starts_at_local"] for s in slots]
        self.assertEqual(len(locals_), len(set(locals_)))
        for amb in ("2026-10-25T02:00", "2026-10-25T02:30"):
            self.assertEqual(locals_.count(amb), 1)
        s0130 = next(s for s in slots
                     if s["starts_at_local"] == "2026-10-25T01:30")
        self.assertEqual(s0130["starts_at"], "2026-10-25T01:30:00+02:00")
        # absolute end: 90 real minutes later -> local 02:00 (+01:00)
        self.assertEqual(s0130["end_instant"].utcoffset(),
                         timedelta(hours=1))
        self.assertEqual(
            s0130["end_instant"].replace(tzinfo=None).strftime("%H:%M"),
            "02:00")
        self.assertEqual(s0130["ends_at_rfc3339"],
                         "2026-10-25T02:00:00+01:00")
        s0200 = next(s for s in slots
                     if s["starts_at_local"] == "2026-10-25T02:00")
        self.assertEqual(s0200["starts_at"], "2026-10-25T02:00:00+02:00")

    def test_fall_back_new_york_first_occurrence(self):
        # NYC 2026-11-01 (sun): 02:00 -> 01:00; first 01:00 is EDT (-04:00).
        rest = _rest(timezone=NYC, opening_hours=[
            {"weekday": "sun", "opens": "00:00", "closes": "05:00"}],
            slot_minutes=60, reservation_duration_minutes=60)
        slots = timeutil.slots_for_day(rest, "2026-11-01")
        s0100 = next(s for s in slots
                     if s["starts_at_local"] == "2026-11-01T01:00")
        self.assertEqual(s0100["starts_at"], "2026-11-01T01:00:00-04:00")


class Helpers(unittest.TestCase):
    def test_overlaps_half_open(self):
        a = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo(BERLIN))
        a_end = timeutil.add_absolute(a, timedelta(minutes=90))
        # 19:00+90 = 20:30; a 20:30 start does NOT overlap.
        b = datetime(2026, 9, 24, 20, 30, tzinfo=ZoneInfo(BERLIN))
        b_end = timeutil.add_absolute(b, timedelta(minutes=90))
        self.assertFalse(timeutil.overlaps(a, a_end, b, b_end))
        self.assertFalse(timeutil.overlaps(b, b_end, a, a_end))
        c = datetime(2026, 9, 24, 20, 29, tzinfo=ZoneInfo(BERLIN))
        self.assertTrue(timeutil.overlaps(
            a, a_end, c, timeutil.add_absolute(c, timedelta(minutes=90))))
        # works on epoch floats too (engineer call sites pass .timestamp())
        self.assertTrue(timeutil.overlaps(
            a.timestamp(), a_end.timestamp(), c.timestamp(),
            timeutil.add_absolute(c, timedelta(minutes=90)).timestamp()))
        self.assertFalse(timeutil.overlaps(
            a.timestamp(), a_end.timestamp(), b.timestamp(), b.timestamp()))

    def test_rfc3339_explicit_offset(self):
        dt = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo(BERLIN))
        self.assertEqual(timeutil.rfc3339(dt), "2026-09-24T19:00:00+02:00")
        utc = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(timeutil.rfc3339(utc), "2026-09-24T17:00:00+00:00")
        self.assertNotIn("Z", timeutil.rfc3339(utc))

    def test_weekday_of(self):
        self.assertEqual(timeutil.weekday_of(BERLIN, "2026-10-01"), "thu")
        self.assertEqual(timeutil.weekday_of(NYC, "2026-10-01"), "thu")
        self.assertEqual(timeutil.weekday_of(BERLIN, "2026-10-25"), "sun")

    def test_add_absolute_across_fall_back(self):
        start = timeutil.resolve_local(BERLIN, "2026-10-25T01:30")
        end = timeutil.add_absolute(start, timedelta(minutes=90))
        self.assertEqual(end.replace(tzinfo=None).strftime("%H:%M"), "02:00")
        self.assertEqual(end.utcoffset(), timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
