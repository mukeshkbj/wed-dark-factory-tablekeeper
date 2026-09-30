@mukeshkbj/tk-experience — STAGE 1 BUILD DISPATCH (part 1/2: complete task instructions; part 2/2 = the COMPLETE official stage-1 specification, next message).

First: read your standing mandate at `D:\WED Dark factory\mandates\tk-experience.md`. Work only in `D:\WED Dark factory`. No human input will come; resolve choices from the spec or argue in the room. This is your substantive stage-1 implementation share (you own the product UI from stage 2).

## What you build — your files ONLY

```
stage-1/src/auth.py        # signup/login, bearer auth, scrypt hashing
stage-1/src/fixtures.py    # /_test/reset fixture parse+apply, seed users+reservations
stage-1/tests/local_checks.py  # stdlib check script vs a running server (BASE_URL env)
stage-1/RUN.md             # build+run docs, hardened mode, demo notes
```

`tk-engineer` owns everything else in `stage-1/` (server, state, domain, Dockerfile). Do not touch their files; do not create stage-2+ content.

## Stack/context (coordinator decision)

Python 3.12 stdlib only. ONE `State` (sqlite3 + one RLock) owned by engineer — linearizable by construction. Engineer lands `src/errors.py` + `src/state.py` skeleton early; write against the contract below immediately — do NOT block waiting for their code.

## Interface contract (fixed — both seats received it verbatim)

- `errors.py` (engineer): `class ApiError(Exception)` with `.status`, `.code`, `.message`. Raise it; never return raw tuples.
- `state.py` (engineer) provides: `insert_user(user_id,email,password_hash,display_name)` raising `ApiError(409,'email_taken')` on duplicate; `user_by_email(email)->dict|None`; `user_by_id(uid)->dict|None`; `insert_token(token,user_id)`; `user_for_token(token)->dict|None`; `reset(fixture)` — atomic replace of ALL state. If any name differs when their skeleton lands, adapt YOUR calls (tell the room).
- `auth.py` MUST expose: `hash_password(pw)->str` (use `hashlib.scrypt`, embed salt+params so `verify_password` is self-contained), `verify_password(pw,stored)->bool` (constant-time compare), `handle_signup(state,body)->dict` (201 body `{user_id,display_name,token}`; validates email `local@domain` + password ≥8 → 422 `validation_failed`, wrong types → raise `ApiError(400,'malformed_request')`), `handle_login(state,body)->dict` (unknown email OR wrong password → 401 `unauthenticated`), `authenticate(state,authorization_header)->user dict` (missing/malformed/unknown → 401). Tokens: `secrets.token_urlsafe`, never expire, multiple per account OK. NEVER store plaintext passwords.
- `fixtures.py` MUST expose: `parse_fixture(body:dict)->Fixture` (dataclass(es) holding `users`, `restaurants`, `reservations`; validate structure — unparseable → `ApiError(400,'malformed_request')`, wrong JSON types → 400 malformed, semantic violations → `ApiError(422,'validation_failed')`) and `handle_reset(state,body)` → calls `state.reset(fixture)` under the store lock, returns None (server sends 204). Seeded users MUST be able to log in immediately — hash their given passwords through `auth.hash_password`. Seeded `reservations` keep their `id`, `reference`, `user_id` verbatim (status `confirmed` unless stated). Fixture restaurants carry `timezone` (IANA), `slot_minutes`, `reservation_duration_minutes`, `cancellation_cutoff_minutes`, `opening_hours`, `tables[{id,label,capacity}]`; a weekday with no entry = closed; IDs ≤64 chars pass through.

## tests/local_checks.py

Stdlib-only script (urllib) against `BASE_URL` (default `http://localhost:8080`). Cover, at minimum: health; reset→reseed; signup+login+401 cases; availability grid math (slot steps, capacity filter, closed day); book→confirm shape+reference charset; overlap → 409; cancel frees slot + repeat cancel 200; cutoff refuse; PATCH amend + failed amend leaves state; idempotency replay 200 same body / different body 409 / freed-after-4xx; concurrent identical posts → exactly one 201 (threads); reservation-moves atomicity incl. failure rollback; export→mutate→import restores (tokens+receipts still valid); DST spot-checks (Berlin 2026-10-25 ambiguous→first, 2026-03-29 nonexistent→invalid_local_time); no 5xx anywhere. Print PASS/FAIL lines + exit code. These are YOUR spec-derived checks — do not copy the shipped suite.

## RUN.md

Exact `docker build` + `docker run -e PORT=... -p ...` commands for `stage-1/`, local dev run, `/health` check, `TK_HARDENED=1` explanation (disables all `/_test/*` → 404; judge image runs WITHOUT it — test endpoints enabled by default), and note state is ephemeral.

## Process

1. Identity: `git -c user.name='TK Experience' -c user.email='tk-experience@local' commit ...`. Stage only your files. No amend/squash/rebase.
2. First commit includes `docs/seats/tk-experience.md` with your session's ACTUAL reported model id (mandate header asks `swe`; coordinator reported `SWE-2 High` — report yours honestly).
3. When engineer posts a skeleton revision, integrate: run your auth/fixtures against their state and reconcile naming in the room if needed.
4. When complete + self-verified: post to the room addressed to @mukeshkbj/tk-verifier with the full committed revision hash and what you verified. Verifier findings route back to you via their handle — fix and post a new revision.

Part 2/2 (FINAL) follows: the complete stage-1 specification.
