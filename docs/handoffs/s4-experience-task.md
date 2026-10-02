@mukeshkbj/tk-experience — STAGE 4 EXPERIENCE/FIXTURE DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-experience.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-4.md`, inherited specs `stage-1.md`/`stage-2.md`/`stage-3.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-4.md` (rulings R4-1..R4-24 are binding).

CONTEXT: stages 1–3 are FROZEN. Stage-3 accepted product tree is `d9d04ba`; verifier evidence through `e5679e3`; coordinator freeze commit `7e957fe`. Engineer will first copy `stage-3/` → `stage-4/` verbatim. Wait for that scaffold commit, then work only in your owned files inside `stage-4/`.

TASK — deliberately narrow:

1. `stage-4/src/fixtures.py`: stage 4 adds no new fixture fields. Preserve the stage-3 `manager_user_ids` validation/default and `combinable`/seed coherence unchanged. Make a change only if a concrete stage-4 fixture coherence issue is found; otherwise leave the file untouched.
2. `demo_seed()`: retain the manager coverage added in stage 3 so replan publication/application can be demonstrated manually. Add seed data only if needed for a coherent demo; no closure fixture field exists in the spec.
3. `stage-4/ui/`: stage 4 explicitly requires **no new screens**. Keep the inherited browser surface byte-stable unless a compatibility fix is truly forced; if so, flag coordinator first. Existing availability, confirmation and lookup screens must reflect an applied plan through the API.
4. Add a focused owned check if practical (for example `stage-4/tests/test_stage4_ui.py`): after engineer's API lands, reset managed demo data, create/book as needed, preview+apply a closure through the API, then verify the existing search grid/lookup reflect the resulting state without a UI regression.
5. `stage-4/tests/test_fixtures.py`: keep/pass inherited fixture tests; add only tests for any fixture change you actually make.
6. `stage-4/SESSION.md`: update the stage/session/model record honestly.

OWNED-BY-OTHERS: `server.py`, `availability.py`, `reservations.py`, `moves.py`, `transfer.py`, `state.py`, `policies.py`, `series.py`, the new replanner/closure logic, and engineer-owned API tests. Do not modify them.

PROCESS: commit early/often, only your files: `git -c user.name='TK Experience' -c user.email='tk-experience@local' commit ...`. Never amend/squash/rebase. Verify locally with `python -m unittest discover -s stage-4/tests`, a `/_test/reset` using `demo_seed()`, and the focused applied-plan browser smoke once the engineer endpoint exists. Message budget is real — no status chatter.

DONE = one handoff message to the room addressed to @mukeshkbj/tk-coordinator: full commit SHA, commands + exit codes + durations, what you did NOT verify, and whether `stage-4/ui/` remained byte-stable. Then end your turn — do not poll.
