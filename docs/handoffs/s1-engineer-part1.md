@mukeshkbj/tk-engineer — STAGE 1 BUILD DISPATCH [PART 1 of 3 — task; the complete official stage-1 spec follows verbatim in parts 2 and 3. You need all three parts before building.]

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-engineer.md` — it governs this whole run. Record the model id your session actually reports (e.g. `band brief --json` / session metadata) in your first committed artifact; the mandate header requested `swe` — report the resolved value honestly.

TASK: implement the Tablekeeper stage-1 JSON API service in `D:\WED Dark factory\stage-1\`. Everything the spec requires: health, `/_test/reset`, `/_test/export`, `/_test/import`, auth signup/login, public restaurants + availability, reservations create/list/get/cancel/PATCH, atomic `/reservation-moves`, idempotency, DST-correct times, plus a `Dockerfile` and `RUN.md` that build and start it in one command.

DECIDED ARCHITECTURE (coordinator ruling; deviate only for a stated reason in your handoff):
- Python 3.12+, **stdlib only** — no pip deps at runtime; `Dockerfile` installs `tzdata` (or relies on Debian zoneinfo) at build. Single image, `python:3.12-slim` or newer base.
- `http.server.ThreadingHTTPServer` (or equivalent) on `0.0.0.0:$PORT` (default 8080).
- All state in memory behind ONE re-entrant writer lock: every check-and-act (availability scan → create; moves batch; cancel; import) is one critical section. This is what makes 50-way concurrency linearizable with zero exotic machinery. Reads may also take the lock; 2 vCPU makes contention fine at this scale.
- Passwords: `hashlib.scrypt` with per-user salt (stdlib, satisfies the spec's scrypt-class requirement). Constant-time compare.
- `zoneinfo` for IANA tz; ambiguous locals resolve to first occurrence (fold=0); nonexistent locals detected via round-trip check.
- Export = deep-copied JSON-serializable snapshot of the whole state under the lock; import validates shape then swaps atomically. Keep ALL state JSON-native so export/import is trivially faithful (idempotency records, tokens, password hashes, reservations, counters).
- Suggested layout (yours to adjust): `stage-1/src/server.py, state.py, errors.py, auth.py, idempotency.py, availability.py, reservations.py, moves.py, transfer.py` + `stage-1/tests/` + `Dockerfile` + `RUN.md`.

OWNED-BY-OTHERS — do not create or modify these files; the experience seat builds them in parallel:
- `stage-1/src/timeutil.py` — DST/local-time/slot-grid math. Contract (already handed to experience; code it against this, stub locally if it hasn't landed):
  - `resolve_local(tz_name: str, local_naive: str) -> datetime` — parse bare `YYYY-MM-DDTHH:MM`, resolve in zone; raise `InvalidLocalTime` for a nonexistent local; ambiguous → first occurrence. Raise `MalformedLocalTime` for any non-bare format (offset, `Z`, seconds, wrong shape).
  - `slots_for_day(rest, date: str) -> list[dict]` — each `{starts_at_local, starts_at, end_instant}` for that date's weekday per spec §8 grid rule (slot+duration ≤ closes); `[]` on closed days; skip nonexistent locals, dedupe ambiguous.
  - `overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool` — half-open.
  - `rfc3339(dt: datetime) -> str` — explicit offset.
  - Exceptions `InvalidLocalTime`, `MalformedLocalTime` live in `timeutil.py`.
- `stage-1/src/fixtures.py` — `validate_fixture(body: dict) -> Fixture`, raising `FixtureError(status, code)` (reset validation failures → 422 `validation_failed`); `demo_seed() -> dict` attractive demo fixture.
- `stage-1/tests/test_timeutil.py`, `stage-1/tests/test_fixtures.py` — their unit tests.
If the modules aren't committed when you need them, write your own local stub in `stage-1/src/_stub_timeutil.py` (name it clearly) so you never block, then swap to the real module on integration. Coordinate the swap in the room.

COORDINATOR RULINGS in `docs/requirements-matrix-stage-1.md` (committed; read it — it is the contract clarification, esp. R-6 validation order, R-7 cutoff boundary `now < starts_at - cutoff`, R-1/R-3 fixture validation → 422, R-4 case-insensitive email uniqueness, R-12 PATCH 404-on-foreign).

TRAPS THE SPEC DEMANDS (non-exhaustive — the spec is the contract):
- Idempotency resolves after JSON-object parse + auth, BEFORE field validation; replay = 200 original body; different body same key = 409 reuse even when the new body is invalid; failed 4xx frees the key; concurrent identical → exactly one 201; replay must return the ORIGINAL response even after cancel/amend.
- Error precedence: unparseable body or wrong JSON type → 400 `malformed_request`, EXCEPT `party_size` (strings/booleans) and `starts_at_local` (non-bare format) which are 422 `validation_failed`; integer query params `1e9`/`4.0`/`+4` → 422; `Idempotency-Key` 1..255 chars else 422.
- `party_size` ordering: check type/integer → `party_exceeds_capacity` needs a found table; unknown restaurant/table/cross-restaurant table → 404.
- Half-open occupancy; cancel frees immediately; double-cancel → 200 current state; PATCH cutoff measured against CURRENT start; failed PATCH leaves occupancy; successful PATCH swaps atomically.
- Import: 422 without state change on bad input; preserves tokens/passwords/receipts/histories; replacement not merge; failed request keys remain reusable.
- Moves: 1..8 distinct string refs; input-order error precedence, cutoff first per booking; all-or-nothing incl. occupancy AND retry keys; 201 + `{"reservations":[...]}` input order; replays return original.
- Never 5xx, ever. Catch-all error handler → never leak a stack trace; map to a 4xx/500-shaped `{"error":{...}}` — but genuinely aim for zero 500s since 5xx is a contract violation.
- `reference`: 6–12 of `[A-Z0-9]`, globally unique, immutable. `created_at`: emit `+00:00`.
- Booking in the past is allowed; cutoff still applies.
- Build to the spec, not to the shipped sample tests — hidden tests exist.

PROCESS: work only inside `stage-1/` (delete the stale `__pycache__` dirs first — they're ignored but clean them). Commit early and often, only your own files: `git -c user.name='TK Engineer' -c user.email='tk-engineer@local' commit ...`. Never amend/squash/rebase. Write your own tests under `stage-1/tests/` — spec-derived, not sample-derived. Verify: service runs locally (`python` or docker), your tests pass, `docker build` works if Docker is up.

DONE = handoff message to the room addressed to the verifier seat (inspect `jam --profile default --session setup chat participants a80cdbce-db3b-4f69-a49f-d0b48119d581` for its exact handle — do not guess): full commit SHA, commands you ran + exit codes + durations, what you did NOT verify, and the module-integration status of timeutil/fixtures. Then end your turn — do not poll.

The complete official stage-1 spec follows in the next two parts.