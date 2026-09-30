# Requirements matrix — tablekeeper stage 1

Coordinator seat (`tk-coordinator`), scored run. Source: `D:\tk-official\tablekeeper\spec\stage-1.md`
@ `803560d`. Every normative clause is a numbered row; rulings on ambiguous sentences are
in §R at the end. Verifier derives its own checks from the spec text — this matrix is the
shared map, not the test list.

## §1 Scope / core invariant

| # | Requirement |
|---|---|
| 1.1 | Search availability, book with confirmation reference, cancel, amend, batch-amend. HTTP API only. |
| 1.2 | **Conservation law:** two `confirmed` reservations never occupy the same table over overlapping time — including under concurrency. Occupancy = half-open `[starts_at, starts_at + reservation_duration)`. A 19:00 90-min booking does NOT overlap a 20:30 start. |
| 1.3 | Retries and rejected requests create no duplicate or partial bookings. |

## §2 Delivery

| # | Requirement |
|---|---|
| 2.1 | `Dockerfile` + `RUN.md`: one command builds+starts, no manual setup. Compose optional, never used by harness. |
| 2.2 | Image runs with `-e PORT=<port>` + port mapping only. No outbound network at runtime (build-time OK). Everything (fonts/scripts/deps/seed) inside the single image. |
| 2.3 | Limits: 2 vCPU, 2 GiB, health within 60 s, 50 concurrent in flight, 5 s/request (10 s `POST /_test/reset` and test-control calls), ephemeral disk OK. |

## §3 Runtime contract

| # | Requirement |
|---|---|
| 3.1 | Listen `0.0.0.0`, `PORT` env, default 8080. |
| 3.2 | `GET /health` → `200 {"status":"ok"}` once store ready. Non-200 allowed before ready. |
| 3.3 | `POST /_test/reset` replaces ALL state with fixture body → 204. Repeated resets OK. Unauthenticated, enabled in delivered image. |
| 3.4 | `application/json; charset=utf-8` req/res. Response timestamps RFC 3339 with explicit offset. Unknown body fields ignored. Unknown query params ignored. IDs opaque ≤64 chars, including fixture-supplied. |

## §4 Model + fixtures

| # | Requirement |
|---|---|
| 4.1 | Restaurants/tables enter only via `/_test/reset`. Fields: `timezone` (IANA), `slot_minutes`, `reservation_duration_minutes`, `cancellation_cutoff_minutes`, `opening_hours` (per weekday, absent day = closed), table `capacity`. |
| 4.2 | `weekday` ∈ `mon..sun`; `opens`/`closes` local `HH:MM`; `closes > opens`, never crosses midnight. |
| 4.3 | Seeded users log in immediately with given password. |
| 4.4 | Seeded `reservations`: POST-body fields + `id`, `reference`, `user_id`. |
| 4.5 | Any calendar date; past starts allowed; cutoffs still apply. |

## §5 Errors

| # | Requirement |
|---|---|
| 5.1 | Every 4xx/5xx: `{"error":{"code":...,"message":...}}` — any wording. |
| 5.2 | Precedence ladder: unparseable body / wrong JSON type → 400 `malformed_request`; missing/empty `Idempotency-Key` → 400 `missing_idempotency_key`; bearer missing/malformed/unknown → 401 `unauthenticated`; authenticated-but-not-owner → 403 `forbidden`; absent/invisible → 404 `not_found`; key reuse w/ different body → 409 `idempotency_key_reuse`; missing required field / violated rule w/o specific code → 422 `validation_failed`. |
| 5.3 | Correct type + bad format/out-of-range → 422 `validation_failed` (incl. invalid dates, negative counts, over-max). |
| 5.4 | Endpoint field rules win: bad `party_size` (incl. strings/booleans) and non-bare `YYYY-MM-DDTHH:MM` `starts_at_local` → 422 `validation_failed` (NOT 400). |
| 5.5 | Integer query params = plain decimal digits only; `1e9`, `4.0`, `+4` → 422 `validation_failed`. |
| 5.6 | `Idempotency-Key` length 1..255, else 422 `validation_failed`. |
| 5.7 | No 5xx ever, including under concurrent load. |

## §6 Auth

| # | Requirement |
|---|---|
| 6.1 | `POST /auth/signup` → 201 `{user_id,display_name,token}`; duplicate email → 409 `email_taken`; password <8 → 422; email not `local@domain` → 422. |
| 6.2 | `POST /auth/login` → 200 same shape; wrong password/unknown email → 401 `unauthenticated`. |
| 6.3 | Bearer required everywhere except `/health`, `/_test/reset`, `/auth/*`, `GET /restaurants`, `GET /restaurants/{id}`, `GET /availability`. |
| 6.4 | Tokens never expire; multiple tokens/sessions per account OK. |
| 6.5 | Passwords hashed (bcrypt/scrypt/Argon2/equivalent). No plaintext storage. |

## §7 Idempotency

| # | Requirement |
|---|---|
| 7.1 | Required on `POST /reservations` and `POST /reservation-moves` only (stage 1). |
| 7.2 | Key scoped to authenticated user; different users' same key strings are independent. |
| 7.3 | Replay = same user + same method + same path + same parsed JSON body (key order/whitespace irrelevant). Same key+body on different path = different request → succeeds normally. |
| 7.4 | Resolution order: body parsed as JSON object → caller authenticated → **idempotency resolved before field validation and current-resource checks** → used key + different body = 409 `idempotency_key_reuse` even if new body invalid. |
| 7.5 | First use → normal response (201). Replay → **200** + body identical to original as JSON value. Different body same key → 409. Key freed after 4xx failure → retry treated as first use. |
| 7.6 | Concurrent identical requests, unused key: exactly one 201; others 200 same body; effect once. |
| 7.7 | Replay returns original response even after resource changed/cancelled; no further state change. |

## §8 API

| # | Requirement |
|---|---|
| 8.1 | `GET /restaurants` public → `{"restaurants":[{id,name,timezone}]}`. |
| 8.2 | `GET /restaurants/{id}` public → fixture shape: slot_minutes, duration, cutoff, opening_hours, tables. Unknown → 404. |
| 8.3 | `GET /availability` public; `restaurant_id`, `date`, `party_size` all required (missing → 422). `date` is restaurant-local. |
| 8.4 | Response: restaurant_id, date, timezone, slots[] each `{starts_at_local, starts_at, available_table_ids}`. `starts_at_local` feeds POST unchanged. |
| 8.5 | Slot per `slot_minutes` step from `opens` while `slot + duration <= closes`. `available_table_ids` = tables with `capacity >= party_size` and no overlapping confirmed reservation, **fixture order**. Empty-available slots still listed. Closed day → `"slots":[]`. |
| 8.6 | `POST /reservations`: body `{restaurant_id,table_id,starts_at_local,party_size}` + key. `starts_at_local` bare `YYYY-MM-DDTHH:MM`, resolved in restaurant tz. |
| 8.7 | 201 response: `reservation_id`, `reference` (6-12 chars A-Z0-9, globally unique, immutable), restaurant_id, table_id, party_size, `status:"confirmed"`, starts_at_local, starts_at, ends_at, created_at (offset timestamps). |
| 8.8 | Errors: overlap → 409 `table_unavailable`; off grid → 422 `not_on_slot_grid`; outside hours / ends after closes → 422 `outside_opening_hours`; party > capacity → 422 `party_exceeds_capacity`; party <1 or non-integer → 422 `validation_failed`; nonexistent local → 422 `invalid_local_time`; unknown restaurant/table or cross-restaurant table → 404 `not_found`. |
| 8.9 | `GET /reservations` → caller's, `starts_at` DESC, confirmed+cancelled, same shape as create response. `{"reservations":[]}` when empty. |
| 8.10 | `GET /reservations/{reference}` → own only; others' → 404 (no existence leak). |
| 8.11 | `POST /reservations/{reference}/cancel` → 200 `{status:"cancelled",...}`; frees table immediately (availability offers slot again). Already cancelled → 200 current state (not error). Within cutoff of start, or later → 409 `cutoff_passed`. Not caller's → 404. |
| 8.12 | `PATCH /reservations/{reference}`: any subset of `{table_id,starts_at_local,party_size}`, NO idempotency key. Same validation as POST; cutoff vs **current** start → 409 `cutoff_passed`; cancelled → 409 `reservation_cancelled`. Success = atomic release-old + reserve-new; failure leaves original untouched. `reference`/`reservation_id` survive. |

## §9 Time/DST

| # | Requirement |
|---|---|
| 9.1 | All local times in restaurant `timezone`; IANA offsets for zone+date. |
| 9.2 | Spring-forward: skipped local times never appear in availability; booking → 422 `invalid_local_time`. |
| 9.3 | Fall-back: repeated hour resolves to FIRST occurrence (pre-transition). Slot appears once; second occurrence unbookable. |
| 9.4 | `reservation_duration_minutes` is ABSOLUTE elapsed time. 90 min from 01:30 on fall-back night → local `ends_at` reads 02:00. |
| 9.5 | Named transitions: Europe/Berlin 2026-03-29 02→03 & 2026-10-25 03→02; America/New_York 2026-03-08 02→03 & 2026-11-01 02→01. Must work for arbitrary zones/dates. |

## §10 Export/Import

| # | Requirement |
|---|---|
| 10.1 | `GET /_test/export` unauthenticated → 200 `{track:"tablekeeper",format_version:1,state:{...opaque...}}`. Atomic read-only snapshot; later writes don't mutate it. |
| 10.2 | `POST /_test/import` takes the whole object → 204; atomically REPLACES state (not merge). Repeat import → same state, no duplication. Accepts this service's own unchanged export; no dependency on source process/files/volume/port. |
| 10.3 | Invalid JSON → §5; missing fields, wrong track/version, invalid state → 422 `validation_failed`, destination unchanged. |
| 10.4 | Preserves: accounts + hashed-password login, live bearer tokens, fixture config, reservations, references, ALL completed idempotent bodies + original responses, identities, statuses, timestamps (never regenerated). Failed keys stay reusable. Import wipes all prior destination data/credentials. Reset still clears imported state. |

## §11 Atomic reservation-moves

| # | Requirement |
|---|---|
| 11.1 | `POST /reservation-moves`: auth + idempotency key. `{"moves":[{reference, table_id?, starts_at_local?, party_size?}, ...]}`. |
| 11.2 | 1..8 items, distinct string refs → else 422 `validation_failed`. All bookings belong to caller AND same restaurant; unknown/other-owner → 404; mixed restaurants → 422. No token → 401. |
| 11.3 | Each item = PATCH fields; omitted fields keep current values; unknown fields ignored. Identity/owner/created_at never change. Cancelled → 409 `reservation_cancelled`. Each booking's own cutoff applies. |
| 11.4 | Error precedence: non-occupancy errors in INPUT ORDER; within a booking, cutoff errors precede other change errors. Then overlap (among resulting bookings or vs unlisted booking) → 409 `table_unavailable`. Unchanged listed bookings keep occupancy. |
| 11.5 | Atomic: every move commits or nothing (occupancy, records, retry keys). 201 `{"reservations":[...]}` in input order incl. unchanged. Replay → 200 original body even after later changes. No-op moves keep all values. Export/import preserves batch receipts + bookings. |

## §R Rulings (coordinator decisions on ambiguous readings)

| # | Ruling | Rationale |
|---|---|---|
| R1 | Error precedence pipeline for write endpoints: (a) unparseable/non-object body → 400 malformed; (b) missing/malformed token → 401; (c) missing/empty Idempotency-Key → 400 missing_idempotency_key; (d) key reuse diff body → 409 reuse, or replay → 200 original; (e) wrong-JSON-type fields → 400 malformed; (f) field format/range → 422 validation_failed (spec-ordered endpoint codes); (g) resource existence/ownership → 404; (h) domain conflicts → 409/422 per table. | §7: "After the body has been parsed ... and the caller authenticated, idempotency is resolved before endpoint-specific field validation or current-resource checks." |
| R2 | Within `POST /reservations` domain checks, order: unknown restaurant/table 404 → `invalid_local_time` → `not_on_slot_grid` → `outside_opening_hours` → `party_exceeds_capacity` → `table_unavailable`. All 422s precede the state-dependent 409. | Existence before evaluation; unresolvable local time blocks grid/hours evaluation; state conflicts last (spec lists table_unavailable as the sole 409). Flagged for verifier adversarial probe — if hidden tests disagree we adjust on evidence. |
| R3 | `GET /availability` unknown `restaurant_id` → 404 `not_found`. | Consistent with §8 restaurant detail 404; resource doesn't exist. |
| R4 | PATCH with no effective field / no-op values → succeeds 200, no error (stage-3 later formalizes "no entry"). | "Any subset" includes empty; a PATCH is still a valid request. |
| R5 | Unauthenticated `GET /reservations/{reference}` → 401 (bearer required), not 404. | §6.3 blanket rule; stage-3 later carves out history/decision only. |
| R6 | `/_test/reset` invalid fixture: unparseable → 400 malformed; wrong-type field → 400 malformed; semantically invalid → 422 validation_failed. Fixture is otherwise authoritative — seeded reservations are stored as given (assumed consistent). | §5 applies to every endpoint; spec never asks reset to reject inconsistent fixtures. |
| R7 | `starts_at`/`ends_at`/`created_at` serialized RFC3339 with offset; `created_at` in UTC (`+00:00`) acceptable. | §3.4 requires explicit offset; example shows Z-form as `+00:00`. |
| R8 | `reservation_id` format ours; ≤64 chars; unique. `reference` 6-12 chars A-Z0-9 (we'll mint 8), unique across all reservations forever. | §8.7. |
| R9 | `ends_at` = `starts_at + duration` as absolute elapsed time (DST-correct). | §9.4. |
| R10 | Cutoff check: `now >= starts_at - cutoff` → refuse (boundary inclusive per "within ... or later"). Applies to cancel and PATCH, measured vs current start for PATCH. | §8.11/§8.12. |
| R11 | Single-writer architecture: ALL state access serialized through one re-entrant lock around a single SQLite connection (or equivalent). Linearizability guaranteed by construction; 50-way concurrency still satisfies 5 s timeout trivially. | Simplest correct enforcement of 1.2/7.6/11.5. |
| R12 | Stack: Python 3.12 stdlib-only (http.server threading, sqlite3, hashlib.scrypt, zoneinfo, secrets). Image `python:3.12-slim`; `tzdata` pip-installed at build if the base image lacks zone files (verify `ZoneInfo("Europe/Berlin")` in-image). UI later = server-rendered HTML + vanilla JS, all assets inline. | Zero runtime deps → nothing to fetch at run time; hashing meets §6.5; zoneinfo meets §9. |
| R13 | `party_size` for availability query: non-digit strings → 422; `0`/negative → 422 validation_failed; huge integers still digits → valid syntax, then capacity rule simply yields empty lists (no max stated). | §5.5 digits rule + §8.3. |
| R14 | `Idempotency-Key` >255 chars → 422 (not 400); empty/whitespace-only? Treat empty string as missing → 400. Whitespace-only non-empty → allowed (spec says "absent or empty"). | §5.6 + §7 header row. |
| R15 | Reservation-moves: validate ALL non-occupancy errors first (input order), then one global overlap check → atomic commit or nothing. Replay stores under the batch key. | §11.4/§11.5. |
| R16 | Fixture-supplied `reference` values are opaque IDs: any non-empty ≤64-char string accepted verbatim; the 6-12 char A-Z0-9 charset binds only references the service generates. Fixture still assumed consistent (unique). | §3.4 "IDs opaque ≤64 chars, including fixture-supplied" + §4.4 vs §8.7; seeds authoritative per R6. Recorded at `4ebb124`; provisional pending verifier's independent review. |

## Concurrency threat list (adversarial sweep seeds for verifier)

- T1: two `POST /reservations` same table/overlapping slot, distinct keys → exactly one 201.
- T2: N identical requests same key+body in flight → exactly one 201, rest 200 same body, one booking.
- T3: PATCH changing table while another PATCH/cancel in flight → serializable outcome.
- T4: moves batch partially overlapping an unlisted booking → whole batch 409, zero changes incl. idempotency ledger.
- T5: cancel frees slot; immediately rebooked by another user — old receipt replay still returns original body.
- T6: reset/import in flight vs ordinary request — requests serialize; no torn reads.
- T7: export mid-write → atomic snapshot (export sees a consistent point).
- T8: key claimed by request that fails 4xx → same key reusable for a different body (first-use).
- T9: fall-back ambiguous slot and spring-forward gap slots — availability omits, booking refuses correctly.
- T10: occupancy boundary — back-to-back bookings (19:00→20:30 and 20:30) must NOT conflict.
