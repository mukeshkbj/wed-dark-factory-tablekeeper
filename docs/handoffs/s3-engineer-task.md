@mukeshkbj/tk-engineer — STAGE 3 BUILD DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-engineer.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-3.md`, inherited specs `stage-1.md`/`stage-2.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-3.md` (rulings R3-1..R3-20 are binding).

CONTEXT: stage-1 is FROZEN; stage-2 is FROZEN by coordinator commit `e4087b6` (`stage-2/` product tree accepted at `5be5343`, verifier evidence `ee28d6b`). This is room `9bf93138-25b0-431d-aa62-4a3dbca30155`. Work only inside `stage-3/` after creating it.

TASK:

1. Create `D:\WED Dark factory\stage-3\` as a verbatim copy of the frozen `stage-2\` tree (exclude `__pycache__`, `.pyc`, generated logs/evidence). First commit: `stage-3 scaffold: verbatim copy of frozen stage-2 @5be5343`.
2. Add state/model support for restaurant policies, reservation history, reservation revisions, accepted terms, restaurant revision, and series. Keep every check-and-act inside the existing single writer lock; no 5xx; failed writes and replays allocate nothing.
3. `GET /availability`: add optional `explain=true` only. Without it, preserve exact stage-2 shape. With it, every slot adds `explain` in fixture order; every table reports `capacity` then `no_overlap`; `available` iff both; `policy_version` selected by local start date. `available_table_ids` and `available_options` still follow stage-2 semantics under the selected policy.
4. Policy endpoints: `POST /restaurants/{id}/policies` manager-only + idempotency; complete immutable policies; policy versions start at 1 per restaurant; failures/replays allocate none. `GET /restaurants/{id}/policies` public, publication order, omits policy 0. Enforce every validation/range in matrix P-1..P-20. Restaurant detail remains original fixture config; decisions use selected policy.
5. Reservation responses: add `revision` and complete `accepted_terms` (selected policy minus `effective_from`). Creation starts revision 1; imported/seeded old bookings normalise to revision 1 + policy-0 terms. Preserve old idempotent response bodies byte-for-byte.
6. History/decision: `GET /reservations/{ref}/history` and `/decision`; owner-only 404 including anonymous. History entries carry seq, at, event, ordered changes, resulting revision, complete accepted_terms. Created/changed/cancelled rules and combined `table_ids` naming follow matrix H-* and B-*.
7. Amendment semantics: real PATCH checks current accepted cutoff first, validates all resulting fields under the resulting date's policy, atomically replaces terms/end/revision/history. No-op PATCH succeeds but changes nothing and records no history. `expected_revision` positive integer only; mismatch → 409 `stale_revision` before cutoff/validation.
8. Series: `POST /series` adopts a confirmed owner anchor within accepted cutoff; count 2..12, interval 1..4. Generate every occurrence atomically at same local time plus interval weeks, each under its own policy/DST/occupancy rules; pair anchors preserve canonical `table_ids`. First failure in index order wins; failure leaves no reservation/history/counter/idempotency state. Return 201 shape and support owner-only `GET /series/{id}`.
9. Series mutations: real individual PATCH marks `exception:true` and bumps series revision once; no-op/failure does not. Cancel bumps series revision once but does not set exception; repeated cancel does not; anchor cancel does not cascade. Replay returns original series response forever.
10. Collective moves: each real item uses individual PATCH semantics; optional per-move `expected_revision`; all-or-nothing; one restaurant revision bump per successful real batch; each changed series occurrence becomes a permanent exception; affected series revisions bump once.
11. Upgrade: import stage-1 and stage-2 exports atomically; preserve users/tokens/reservations/references/idempotent bodies+responses; normalise missing stage-3 fields per R3-20; stage-3 export/import round-trips all new fields.
12. Keep hardened mode (`TK_HARDENED=1` disables `/_test`) and update `stage-3/RUN.md`, Dockerfile if needed, and `stage-3/SESSION.md` with your resolved model.

OWNED-BY-OTHERS: `stage-3/src/fixtures.py`, `stage-3/src/timeutil.py`, `stage-3/ui/**`, and experience-owned fixture/UI tests. Do not create/modify them. If their contract blocks you, flag coordinator instead of editing.

TRAPS: policy publication never retroactively edits bookings; `explain` describes tables only; `available_options` remains present; `table_ids` canonical order; old responses replay unchanged; history/decision return 404 even without auth; anonymous policy list remains public; count/interval booleans invalid; series failure must free the idempotency key; restaurant revision increments once per real write/batch only.

VERIFY before handoff: run focused stage-3 tests plus inherited `python -m unittest discover -s stage-3/tests`; exercise host service manually for at least policy→availability explain→book→history/decision→series→import. Docker build if Docker is up.

DONE = one handoff message to the room addressed to @mukeshkbj/tk-coordinator: full commit SHA, commands + exit codes + durations, what you did NOT verify, and fixtures/UI integration status. Then end your turn — do not poll.
