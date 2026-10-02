@mukeshkbj/tk-engineer — STAGE 4 BUILD DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-engineer.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-4.md`, inherited specs `stage-1.md`/`stage-2.md`/`stage-3.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-4.md` (rulings R4-1..R4-24 are binding).

CONTEXT: stages 1–3 are FROZEN. Stage-3 was frozen by coordinator commit `7e957fe`; the accepted `stage-3/` product tree is `d9d04ba`, with verifier evidence through `e5679e3`. This is room `9bf93138-25b0-431d-aa62-4a3dbca30155`. Work only inside `stage-4/` after creating it.

TASK:

1. Create `D:\WED Dark factory\stage-4\` as a verbatim copy of the frozen `stage-3\` tree (exclude `__pycache__`, `.pyc`, generated logs/evidence). First commit: `stage-4 scaffold: verbatim copy of frozen stage-3 @d9d04ba`.
2. Add state/model support for replan plans and applied closures. Keep every check-and-act inside the existing single writer lock; no 5xx; failed writes and replays allocate nothing.
3. Implement `POST /restaurants/{id}/replans` exactly per RP-* and R4-*:
   - manager auth + idempotency;
   - explicit-offset `from`/`to`, half-open absolute interval, `from < to`;
   - considered set = confirmed same-restaurant bookings overlapping the closure;
   - deterministic limits (6 tables / 4 declared pairs / 6 considered bookings → 422 `planning_limit` above);
   - candidate options = singles in fixture order then declared pairs in declared order;
   - capacity under each booking's own accepted terms;
   - no conflicts with fixed bookings, other assignments, prior closures, or proposed closure;
   - lexicographic optimization: moved count, unused seats, option-rank vector by reference order;
   - preview stores the plan only, returns current restaurant revision, changes no occupancy/history/revisions;
   - 409 `no_feasible_plan` on failure.
4. Implement `POST /restaurants/{id}/replans/{plan_id}/apply`:
   - manager auth + idempotency, `{}` body;
   - unknown/wrong-restaurant plan → 404;
   - stale restaurant revision → 409 `stale_plan`;
   - already-applied under different key → 409 `plan_already_applied`; successful replay → original 200 response;
   - atomic closure + assignment write; one restaurant revision increment;
   - moved bookings get one revision bump and one `reassigned` history entry with `table_ids` change + top-level `plan_id`; terms/times unchanged;
   - moved series occurrences preserve exception flags and bump each affected series revision once.
5. Make applied closures occupancy constraints across availability, explain, creates, PATCH, moves, series adoption/amendment, and later replans. Conflicting writes return 409 `table_unavailable`; `explain.no_overlap` is false for a closure conflict.
6. Implement `POST /series/{series_id}/amend` per SA-*:
   - owner-only idempotent write; required `expected_revision`, `from_index`, `local_time`;
   - stale series revision before occurrence validation;
   - eligible indices ≥ `from_index`, excluding cancelled and exception occurrences;
   - same-date clock-time amendment retaining current canonical table selection and party size;
   - per-occurrence cutoff then resulting-date policy; batch occupancy including unchanged occurrences and closures;
   - atomic all-or-nothing; once-per-operation series/restaurant revision bumps; no exception marks;
   - all-no-op/empty eligible set succeeds without revision changes;
   - replay returns original response with 200 forever.
7. Upgrade/import: accept stage-1/2/3 exports; stage-4 export/import must preserve pending/applied plans, closures, series, histories, revisions, terms, idempotency and counters needed for behavior/replay.
8. Keep hardened mode (`TK_HARDENED=1` disables `/_test`) and update `stage-4/RUN.md`, Dockerfile if needed, and `stage-4/SESSION.md` with your resolved model.

OWNED-BY-OTHERS: `stage-4/src/fixtures.py`, `stage-4/src/timeutil.py`, `stage-4/ui/**`, and experience-owned fixture/UI tests. Do not create/modify them. If their contract blocks you, flag coordinator instead of editing.

TRAPS: previews do not bump restaurant revision; apply response carries the post-bump revision; closure strings echo the accepted request while behavior uses instants; replay beats stale/plan state; `plan_already_applied` wins over `stale_plan` for an applied plan; reassigned history always uses `table_ids`, even single→single; closure on one table blocks pairs containing it; no diner cutoff blocks an operator repair; series amend checks series expected_revision, not reservation revisions.

VERIFY before handoff: run focused stage-4 tests plus inherited `python -m unittest discover -s stage-4/tests`; exercise host service manually for at least manager preview→write-invalidate/apply→availability/explain, series amend, import/export, and a failed all-or-nothing path. Docker build if Docker is up.

DONE = one handoff message to the room addressed to @mukeshkbj/tk-coordinator: full commit SHA, commands + exit codes + durations, what you did NOT verify, and fixtures/UI integration status. Then end your turn — do not poll.
