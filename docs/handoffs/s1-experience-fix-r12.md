@mukeshkbj/tk-experience — STAGE-1 REPAIR DISPATCH (1 part, complete). Ruling R-12 (committed, `docs/requirements-matrix-stage-1.md` @ `182fd8c`).

Your `stage-1/src/fixtures.py` over-validates relative to spec §4 (flagged by the engineer seat, confirmed by me):

1. `table.label` is OPTIONAL — §4's normative field table names only `capacity` for tables; `label` appears in the JSON example but has no stated rule. Fix: if `label` is absent, accept and default display to the table `id`; if present and not a string → 422 `validation_failed`.
2. `table.capacity` — accept integers `>= 0`; only negative → 422. A 0-capacity table is legal (it just can never hold a party).
3. `cancellation_cutoff_minutes` — accept integers `>= 0` (0 = amendable up to the start instant); only negative → 422. It currently sits in the shared `r[key] < 1` check — pull it out.
4. Keep `slot_minutes >= 1` and `reservation_duration_minutes >= 1` (structural: a zero grid cannot enumerate; zero duration is meaningless).

Then: update your `tests/test_fixtures.py` — any case asserting rejection of missing label / capacity 0 / cutoff 0 must now assert acceptance, and add cases for the new acceptances plus negative-value rejections. Run `python -m unittest discover -s stage-1/tests -v` and report exit code. Commit ONLY your owned files (`stage-1/src/fixtures.py`, `stage-1/tests/test_fixtures.py`, plus this module's demo seed if touched) as TK Experience.

This must land before the verifier's phase-2 gate completes — the validator feeds `_test/reset`, which every hidden fixture flows through. Reply to me when committed with the SHA; end your turn after.
