@mukeshkbj/tk-engineer — REPAIR DISPATCH R-12 (reassigned from tk-experience; its runtime is stalled in a permission loop — operator-confirmed). You are live and just landed R-13 cleanly; same drill. 1 part, complete.

`stage-1/src/fixtures.py` over-validates vs spec §4 (ruling R-12 @ `182fd8c`, matrix @ `docs/requirements-matrix-stage-1.md`). The normative table field is only `capacity`; nothing forbids missing labels or zero values.

Changes (fixtures.py only):
1. `label` — optional. If present, validate `isinstance(str)`; do NOT _fail when absent.
2. `capacity` — currently `t["capacity"] < 1` → allow `>= 0` (`capacity < 0` fails; `== 0` ok).
3. `cancellation_cutoff_minutes` — currently `< 1` → allow `>= 0`.

Tests (`stage-1/tests/test_fixtures.py`): add positives — table with no `label` validates; `capacity: 0` validates; `cancellation_cutoff_minutes: 0` validates. Keep negatives (`capacity: -1`, non-int capacity, wrong-type label → 422).

Run `python -m unittest discover -s stage-1/tests -v` → report exit code. Commit as TK Engineer; reply with SHA. Do NOT touch auth.py (R-13 done) or timeutil.py. End turn after posting.
