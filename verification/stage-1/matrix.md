# Verifier matrix — Tablekeeper stage-1

Independent clause-by-clause matrix derived from the official spec file `stage-1.md`
(official kit @ 803560d2a678ace1414465c098eb0ab5380ffade) text ONLY — not from the
shipped sample suite or the implementation. Check IDs map to `verification/stage-1/checks.py`.
Author: tk-verifier. Every verdict names an exact commit.

Fixture used by checks.py: `r_anker` (Europe/Berlin, slot 30, dur 90, cutoff 120,
thu 18:00-23:00 / fri 18:00-23:30 / sun 01:00-06:00, tables t_1 cap2 / t_2 cap4);
`r_ny` (America/New_York, slot 30, dur 60, cutoff 60, sun 00:00-05:00, t_a cap2 / t_b cap4);
`r_empty` (Berlin, no opening hours); seeded users u_ada / u_bob.

## SS1 Scope invariants

| ID | Requirement | Check |
|---|---|---|
| INV-1 | Two confirmed reservations never overlap same table; half-open [starts_at, starts_at+duration); 19:00+90min does not overlap 20:30 | C-AV-4 boundary adjacency; C-BK-1 overlap 409; C-CON-2 race |
| INV-2 | Retries and rejected requests create no duplicate/partial bookings | C-IDM-*, C-MOV-8 rollback |

## SS2/SS3 Runtime contract

| ID | Requirement | Check |
|---|---|---|
| RT-1 | Listen 0.0.0.0:$PORT default 8080; healthy <=60s; <=50 in-flight; 5s/req (10s reset); no outbound at run | harness build/run; C-RT-1 health; C-CON-1 50-way |
| RT-2 | `GET /health` -> 200 `{"status":"ok"}` | C-RT-1 |
| RT-3 | `POST /_test/reset` -> 204, replaces ALL state, repeatable, unauthenticated; after reset only fixture visible (old tokens die) | C-RT-2..4 |
| RT-4 | JSON `application/json; charset=utf-8`; timestamps RFC3339+offset; unknown body fields ignored; unknown query params ignored; IDs opaque <=64 chars | C-RT-5, C-ERR-9; 65-char fixture id -> see GAP-1 |

## SS4 Model / fixture

| ID | Requirement | Check |
|---|---|---|
| FX-1 | Seeded users log in immediately with fixture password | C-AU-6 |
| FX-2 | Seeded reservations occupy tables (fields = POST body + id/reference/user_id) | C-AV-5 |
| FX-3 | Past-date bookings not rejected solely for being past (cutoff still applies to cancel/amend) | C-BK-8, C-CN-5 |
| FX-4 | Days without opening_hours entry are closed; closes > opens same day | C-AV-6 |

## SS5 Errors

| ID | Requirement | Check |
|---|---|---|
| ERR-1 | Every 4xx/5xx body `{"error":{"code","message"}}` | asserted inside every error check |
| ERR-2 | Unparseable body or wrong JSON type -> 400 `malformed_request` | C-ER-1..3 |
| ERR-3 | Missing/empty Idempotency-Key -> 400 `missing_idempotency_key` | C-ER-4 |
| ERR-4 | Missing/malformed/unknown bearer -> 401 `unauthenticated` | C-ER-5, C-AU-8 |
| ERR-5 | 404 `not_found` also covers "not visible to caller" | C-BK-7, C-CN-4 |
| ERR-6 | Missing required field/param, out-of-range, bad format -> 422 `validation_failed` | C-ER-6..8 |
| ERR-7 | Endpoint precedence: `party_size` of ANY invalid value incl. string/bool/float -> 422 (not 400); non-bare `starts_at_local` -> 422 | C-BK-4, C-BK-5 |
| ERR-8 | Integer query params plain digits only: `+4`, `4.0`, `1e9`, `-1`, `x` -> 422 | C-AV-8 |
| ERR-9 | Idempotency-Key 1..255 chars; empty -> 400 (absent/empty); 256 -> 422; 255 ok | C-ER-4, C-IDM-9 |
| ERR-10 | No 5xx ever, incl. concurrent load | all probes assert status<500; C-FZ-1 fuzz |
| ERR-11 | Precedence pipeline: parse -> auth -> key-present -> ledger -> types(400) -> missing/format(422) -> existence(404) -> domain(422/409); used-key+different-body -> 409 BEFORE validation | C-PP-1..6 |

## SS6 Auth

| ID | Requirement | Check |
|---|---|---|
| AU-1 | signup -> 201 `{user_id,display_name,token}`; token usable | C-AU-1 |
| AU-2 | login -> 200 same shape | C-AU-2 |
| AU-3 | duplicate email (incl. seeded) -> 409 `email_taken` | C-AU-3 |
| AU-4 | password <8 -> 422; =8 ok | C-AU-4 |
| AU-5 | email not `local@domain` -> 422 | C-AU-5 |
| AU-6 | wrong password / unknown email -> 401 `unauthenticated` | C-AU-6 |
| AU-7 | Bearer required everywhere except /health, /_test/*, signup, login, GET /restaurants{,/id}, /availability | C-AU-8 (each protected route) |
| AU-8 | Tokens do not expire; multiple concurrent tokens valid | C-AU-7 |
| AU-9 | Passwords hashed (scrypt/bcrypt/argon2/equiv); never plaintext — incl. inside export artifact | C-AU-9 (export scan) + diff review |

## SS7 Idempotency

| ID | Requirement | Check |
|---|---|---|
| IDM-1 | Required on POST /reservations + /reservation-moves | C-ER-4 (both) |
| IDM-2 | Key scoped to authenticated user; same key across users independent | C-IDM-6 |
| IDM-3 | Replay = same user+method+path+same parsed body; same key+body other path = distinct request (not 409-reuse) | C-IDM-5 |
| IDM-4 | Ledger resolved after parse+auth, BEFORE field validation/resource checks | C-PP-5 |
| IDM-5 | First use -> 201; replay -> 200 identical JSON value | C-IDM-1 |
| IDM-6 | Same key different body -> 409 `idempotency_key_reuse` | C-IDM-2 |
| IDM-7 | Key reuse after 4xx -> treated as first use | C-IDM-3 |
| IDM-8 | "Same body" = same JSON value (key order/whitespace irrelevant) | C-IDM-4 |
| IDM-9 | Concurrent identical requests, unused key: exactly one 201, others 200 same body; effect once | C-CON-1 (50-way) |
| IDM-10 | Replay returns ORIGINAL response even after resource changed/cancelled; no further state change | C-IDM-7, C-IDM-8 |

## SS8 API

| ID | Requirement | Check |
|---|---|---|
| API-1 | `GET /restaurants` public -> `{restaurants:[{id,name,timezone}]}` | C-AV-1 |
| API-2 | `GET /restaurants/{id}` public, fixture shape incl. opening_hours+tables; unknown -> 404 | C-AV-2 |
| API-3 | `GET /availability` public; all of restaurant_id/date/party_size required, missing -> 422 | C-AV-3 |
| API-4 | Slot per `slot_minutes` step from opens with slot+dur <= closes; `starts_at_local` full `YYYY-MM-DDTHH:MM`; `starts_at` RFC3339+offset | C-AV-4 |
| API-5 | `available_table_ids`: capacity >= party_size AND no overlapping confirmed, fixture order; empty list still appears | C-AV-5, C-AV-7 |
| API-6 | Closed day -> `"slots": []` | C-AV-6 |
| API-7 | `POST /reservations` 201 shape: reservation_id, reference, restaurant_id, table_id, party_size, status confirmed, starts_at_local, starts_at, ends_at, created_at | C-BK-1 |
| API-8 | `reference` 6-12 chars `[A-Z0-9]`, globally unique, never changes | C-BK-2, C-PT-5 |
| API-9 | Booking errors: overlap -> 409 `table_unavailable`; off-grid -> 422 `not_on_slot_grid`; outside hours/end>closes -> 422 `outside_opening_hours`; party>capacity -> 422 `party_exceeds_capacity`; party<1/non-int -> 422 `validation_failed`; nonexistent local -> 422 `invalid_local_time`; unknown restaurant/table/foreign-restaurant table -> 404 | C-BK-3..7, C-DST-2 |
| API-10 | `GET /reservations` = caller's only, starts_at desc, confirmed+cancelled, create shape | C-LS-1..3 |
| API-11 | `GET /reservations/{reference}` own -> 200; other user's/unknown -> 404 | C-BK-7 |
| API-12 | cancel -> 200 `{status:cancelled}`; frees table immediately; already-cancelled -> 200 current state; now within cutoff or later -> 409 `cutoff_passed`; not caller's -> 404 | C-CN-1..5 |
| API-13 | PATCH: subset {table_id,starts_at_local,party_size}; no key; create-identical validation; cutoff vs CURRENT start; cancelled -> 409 `reservation_cancelled`; success releases old+reserves new atomically; failure leaves original unchanged; reference+reservation_id survive | C-PT-1..5 |
| API-14 | PATCH/cancel on other user's -> 404 | C-PT-4 |

## SS9 Time & DST

| ID | Requirement | Check |
|---|---|---|
| DST-1 | Spring-forward nonexistent locals never in availability; booking -> 422 `invalid_local_time` (Berlin 2026-03-29, NY 2026-03-08) | C-DST-1,2,5 |
| DST-2 | Fall-back ambiguous locals resolve to FIRST occurrence; slot once; 2nd occurrence not bookable (Berlin 2026-10-25, NY 2026-11-01) | C-DST-3,6 |
| DST-3 | Duration absolute: 90min from 01:30 on fall-back -> local ends_at reads 02:00 | C-DST-4 |
| DST-4 | IANA offsets for zone+date in all emitted timestamps | asserted throughout |
| DST-5 | Cross-transition occupancy uses absolute instants (02:30 first-occurrence vs 01:30+90 overlap -> 409) | C-DST-7 |

## SS10 Export / import

| ID | Requirement | Check |
|---|---|---|
| XFR-1 | `GET /_test/export` -> 200 `{track:"tablekeeper",format_version:1,state}`; unauthenticated; atomic read-only snapshot | C-XF-1, C-XF-9 |
| XFR-2 | `POST /_test/import` takes entire export object -> 204, atomic replace; accepts own unchanged export; no dependency on source process/port/files | C-XF-2 |
| XFR-3 | Replacement not merge: destination data+credentials wiped; repeated import idempotent | C-XF-3, C-XF-4 |
| XFR-4 | Invalid JSON -> 400; missing fields/wrong track/version/invalid state -> 422; destination unchanged | C-XF-5 |
| XFR-5 | Preserves: accounts+hashed login, live bearer tokens, fixture config, reservations, references, ALL idempotent bodies+original responses; ids/statuses/timestamps not regenerated; failed keys remain reusable | C-XF-2, C-XF-6..8 |
| XFR-6 | Reset still clears imported state | C-XF-8 |

## SS11 Atomic reservation moves

| ID | Requirement | Check |
|---|---|---|
| MOV-1 | auth + Idempotency-Key required (401/400) | C-MV-1 |
| MOV-2 | `moves` 1..8 objects, distinct string refs; bad shape/dup -> 422 | C-MV-2 |
| MOV-3 | All caller's + same restaurant; unknown/foreign -> 404; cross-restaurant -> 422 | C-MV-3 |
| MOV-4 | Items accept PATCH fields; omitted retain; unknown ignored; identity/owner/created_at never change | C-MV-4,7 |
| MOV-5 | Cancelled booking -> 409 `reservation_cancelled`; per-booking cutoff applies (`cutoff_passed`) | C-MV-5 |
| MOV-6 | Non-occupancy errors take precedence in INPUT ORDER; cutoff precedes other errors for that booking | C-MV-6 |
| MOV-7 | Overlap among resulting bookings or with unlisted booking -> 409 `table_unavailable`; unchanged listed bookings retain occupancy | C-MV-7 |
| MOV-8 | All-or-nothing: occupancy, records, retry keys; failed batch key remains reusable | C-MV-8 |
| MOV-9 | Success -> 201 `{"reservations":[...]}` input order incl. unchanged; replay -> 200 original even after later changes | C-MV-9 |
| MOV-10 | No-op moves retain values; export/import preserves batch receipts + bookings | C-MV-9, C-XF-8 |

## Explicit coverage gaps (honest limits)

- GAP-1: fixture IDs >64 chars rejection — spec says limit "applies to IDs supplied in reset
  fixtures" but names no error code; flagged for harness/diff review, not asserted.
- GAP-2: cutoff boundary at EXACTLY `cancellation_cutoff_minutes` before start ("within ... or
  later" read as inclusive) tested at +/-1min around boundary, not the instant — real-clock
  races make an exact-equality probe flaky.
- GAP-3: 50-in-flight budget verified at API level (threads), socket-level backlog not measured.
- GAP-4: 2 vCPU/2 GiB and 60s-start verified by official harness/Docker, not by my probes.
- GAP-5: `email` edge forms beyond clear non-`local@domain` strings (e.g. `a@b`, unicode local
  parts) left unasserted — spec only fixes the stated form.
- GAP-6: 5xx-avoidance swept on the paths exercised; not an exhaustive input-space proof.
