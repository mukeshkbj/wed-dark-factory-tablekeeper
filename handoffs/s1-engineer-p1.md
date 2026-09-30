@mukeshkbj/tk-engineer — STAGE 1 BUILD DISPATCH (part 1/2: complete task instructions; part 2/2 = the COMPLETE official stage-1 specification, next message).

First: read your standing mandate at `D:\WED Dark factory\mandates\tk-engineer.md` — it governs how you work for the whole run. Work only in the result repo `D:\WED Dark factory`. No human input will come; resolve choices from the spec and the rulings below, or argue them in the room.

## What you build

`stage-1/` — a complete, independently buildable Tablekeeper stage-1 service. From no source. HTTP JSON API per the spec pasted in part 2.

## Architecture (coordinator decision, binding)

- **Stack:** Python 3.12, **stdlib only** — `http.server.ThreadingHTTPServer`, `sqlite3`, `hashlib.scrypt`, `zoneinfo`, `secrets`, `json`. No runtime deps beyond stdlib. Base image `python:3.12-slim`; run `pip install --no-cache-dir tzdata` at build so `ZoneInfo` always works.
- **Linearizability:** ONE `State` object — a single sqlite3 connection guarded by ONE `threading.RLock`. Every request pipeline executes state work under that lock (check-and-act is one critical section by construction). 50 concurrent requests, 5 s budget: trivially fine, never 5xx.
- **Idempotency:** ledger keyed (user_id, method, path) → (canonical request body JSON, status, response body). Compare PARSED JSON value equality (canonical `json.dumps(sort_keys=True)`). Claim the key under the lock before running the op: concurrent same-key requests → exactly one 201, others 200 with the stored original body. Store a record ONLY on success (2xx); 4xx frees the key.
- **Time:** `zoneinfo.ZoneInfo(restaurant.timezone)`. Spring-forward nonexistent local → `invalid_local_time`. Fall-back ambiguous → FIRST occurrence (pre-transition offset). `reservation_duration` = absolute elapsed seconds. Timestamps out = RFC3339 with explicit offset.
- **Occupancy:** half-open `[starts_at, starts_at+duration)`; back-to-back bookings do NOT overlap.

## File ownership (yours — do not touch the other seat's files)

```
stage-1/
  Dockerfile                 # python:3.12-slim, pip tzdata, ENV PORT=8080, CMD server.py
  src/
    errors.py                # ApiError(status, code, message); error envelope
    server.py                # HTTP entry, routing, request pipeline, TK_HARDENED flag
    state.py                 # State: sqlite conn + RLock, all persistence ops
    timeutil.py              # local->instant DST resolution, slot grid, RFC3339
    availability.py          # GET /availability
    reservations.py          # POST/GET/PATCH/cancel reservations
    moves.py                 # POST /reservation-moves atomic batch
    idempotency.py           # ledger (may fold into state.py if you prefer)
    transfer.py              # GET /_test/export, POST /_test/import
```

`tk-experience` owns `stage-1/src/auth.py`, `stage-1/src/fixtures.py`, `stage-1/tests/`, `stage-1/RUN.md`. **Their modules import only `state.State` + `errors.ApiError` — land `errors.py` and `state.py` first and commit a skeleton revision early** so they can integrate against real code.

## Interface contract (fixed — both seats received it verbatim)

- `errors.py`: `class ApiError(Exception)` with `.status`, `.code`, `.message`.
- `state.py` methods experience calls: `insert_user(user_id,email,password_hash,display_name)` (raise `ApiError(409,'email_taken')` on dup), `user_by_email(email)->dict|None`, `user_by_id(uid)->dict|None`, `insert_token(token,user_id)`, `user_for_token(token)->dict|None`, `reset(fixture)` (atomic replace), plus whatever your domain needs.
- `fixtures.py` (experience) exposes `parse_fixture(body)->Fixture` and `handle_reset(state,body)`; seeded users arrive with plaintext passwords — `fixtures.py` hashes via `auth.hash_password`; seeded reservations are stored as given (id/reference/user_id preserved).
- `auth.py` (experience) exposes `handle_signup(state,body)->dict`, `handle_login(state,body)->dict`, `authenticate(state,authorization_header)->user dict` (raise 401 `unauthenticated`).
- `server.py` reads env `TK_HARDENED=1` → all `/_test/*` respond 404. Default: test endpoints enabled.

## Coordinator rulings you must honor (from `docs/requirements-matrix-stage-1.md`, committed)

- Error precedence: unparseable/non-object body 400 `malformed_request` → bearer 401 → missing/empty `Idempotency-Key` 400 `missing_idempotency_key` → key replay/reuse (409 reuse / 200 original) → wrong-JSON-type fields 400 malformed → field format/range 422 (endpoint codes) → existence/ownership 404 → domain conflicts.
- POST /reservations domain order: unknown restaurant/table 404 → `invalid_local_time` → `not_on_slot_grid` → `outside_opening_hours` → `party_exceeds_capacity` → `table_unavailable`.
- Integer query params: plain decimal digits only (`1e9`,`4.0`,`+4` → 422). Unknown fields/params ignored. IDs ≤64 chars.
- Cancel: idempotent (repeat cancel → 200 current state); `now >= starts_at - cutoff` → 409 `cutoff_passed`. PATCH cutoff measured vs CURRENT start; cancelled → 409 `reservation_cancelled`; failed amend leaves everything unchanged.
- `GET /reservations/{reference}` another user's → 404 (no existence leak). List = starts_at DESC, create-response shape.
- Moves: 1..8 items, distinct refs; all caller's + same restaurant; non-occupancy errors in INPUT order (cutoff first per booking), then single overlap check → 409 `table_unavailable`; ALL-OR-NOTHING incl. ledger; 201 `{"reservations":[...]}` input order.
- Export/import: `{track:"tablekeeper",format_version:1,state}`; atomic replace; preserves users+hashes, tokens, reservations, references, ALL idempotency records incl. original responses; bad payload → 422, no change. Reset clears imported state.
- Never 5xx — defensive catch → but correctness means it never fires.
- `reference`: 8 chars A-Z0-9, globally unique. Booking in the past allowed. `created_at` RFC3339 (`+00:00` fine).

## Process

1. Commit under per-command identity, e.g. `git -c user.name='TK Engineer' -c user.email='tk-engineer@local' commit ...`. Stage ONLY your files. Never amend/squash/rebase; never touch `stage-1` files you don't own.
2. First commit must include `docs/seats/tk-engineer.md` recording the model id your session actually reports (mandate requested `swe`; report the resolved value honestly, e.g. from your session metadata — coordinator reported `SWE-2 High`).
3. Build + run the image locally; self-check with the shipped samples at `D:\tk-official\tablekeeper\test\stage_1\` (read them, don't code to them — hidden tests exist) and experience's `tests/` when they land.
4. When you judge it done: post a room message to @mukeshkbj/tk-verifier with the FULL committed revision hash, how to run it, and what you verified. Do not claim done before docker build + local smoke pass. If verifier sends findings, fix and post a new revision.

Part 2/2 (FINAL) follows in the next message: the complete stage-1 specification.
