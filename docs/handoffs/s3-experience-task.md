@mukeshkbj/tk-experience — STAGE 3 EXPERIENCE/FIXTURE DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-experience.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-3.md`, inherited specs `stage-1.md`/`stage-2.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-3.md` (rulings R3-1..R3-20 are binding).

CONTEXT: stage-1 is FROZEN; stage-2 is FROZEN by coordinator commit `e4087b6` (`stage-2/` product tree accepted at `5be5343`, verifier evidence `ee28d6b`). Engineer will first copy `stage-2/` → `stage-3/` verbatim. Wait for that scaffold commit, then work only in your owned files inside `stage-3/`.

TASK — deliberately narrow:

1. `stage-3/src/fixtures.py`: add optional restaurant `manager_user_ids` validation/default per R3-2:
   - absent → `[]`;
   - must be a list of existing user ids from the fixture's `users`;
   - entries are strings within the stage-1 id limit;
   - duplicate equivalent entries collapse to first-declared order;
   - malformed/unknown/non-string/over-length entries are invalid fixture content → `FixtureError` → 422 `validation_failed`, state unchanged.
   Keep every existing stage-1/stage-2 fixture rule unchanged, including `combinable` and seeded `table_ids` coherence.
2. `demo_seed()`: keep the existing attractive hospitality fixture coherent and add manager coverage — at least one seeded user id listed in `manager_user_ids` on a restaurant so policy publication can be demonstrated. Do not weaken existing users/reservations/combinable seed checks.
3. `stage-3/tests/test_fixtures.py`: add focused tests for `manager_user_ids` default, valid list, duplicate collapse, malformed shape/type, unknown user id, and state-unchanged reset failure if practical.
4. `stage-3/SESSION.md`: update the stage/session/model record honestly.
5. UI: stage-3 explicitly requires **no new screens** for explanations/history. Do not redesign or add manager screens. The copied stage-2 UI should remain byte-stable unless a tiny compatibility fix is truly forced; if so, flag coordinator first.

OWNED-BY-OTHERS: `server.py`, `availability.py`, `reservations.py`, `moves.py`, `transfer.py`, `state.py`, all policy/history/series logic, and `stage-3/ui/**` unless coordinator explicitly reopens UI work.

PROCESS: commit early/often, only your files: `git -c user.name='TK Experience' -c user.email='tk-experience@local' commit ...`. Never amend/squash/rebase. Verify locally with `python -m unittest discover -s stage-3/tests` and a `/_test/reset` using `demo_seed()`. Message budget is real — no status chatter.

DONE = one handoff message to the room addressed to @mukeshkbj/tk-coordinator: full commit SHA, commands + exit codes + durations, what you did NOT verify, and integration assumptions for `manager_user_ids`. Then end your turn — do not poll.
