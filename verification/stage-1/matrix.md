# Stage-1 coverage matrix — tk-verifier (spec-derived)

Derived from spec §1–§11 verbatim text only. Every testable clause → a `V-*`
requirement → planned `C-*` check ids implemented in `checks.py` /
`model.py`. Status column: `written` = check authored, `pending` = runs in
Phase 2, `gap` = not verifiable black-box / needs coordinator ruling.

## V1 Scope (§1)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V1-1 | No two `confirmed` reservations overlap on one table; half-open `[starts_at, starts_at+duration)`; 19:00+90m does not overlap 20:30 | C-BND-1..3, C-CON-* , M-OCC | written |
| V1-2 | Holds under concurrency (≤50 in flight) | C-CON-1 (25 identical), C-CON-2 (25 conflicting), C-CON-3 (conservation post-check) | written |
| V1-3 | Retries/rejections create no duplicate/partial bookings | C-IDM-*, C-ATM-* | written |
| V1-4 | Clean-room (no external product source) | n/a — process | gap |

## V2 Delivery & limits (§2)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V2-1 | Dockerfile + RUN.md, one command builds/starts, compose optional & unused | Phase-2 manual build | pending |
| V2-2 | `-e PORT=<port>` + mapping; listen 0.0.0.0; default 8080 | Phase-2 docker run | pending |
| V2-3 | No outbound network at runtime | isolated harness mode | pending |
| V2-4 | 2vCPU/2GiB; healthy ≤60s; ≤50 concurrent; 5s/req (10s reset) | C-PERF-1 (latency), harness | written/pending |
| V2-5 | All runtime assets in image | isolated mode | pending |

## V3 Runtime contract (§3)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V3-1 | `GET /health` → 200 `{"status":"ok"}` when ready (≤60s); non-200 pre-ready ok | C-RT-1 | written |
| V3-2 | `POST /_test/reset` fixture → 204; replaces ALL state; repeatable; no auth | C-RT-2..4 | written |
| V3-3 | `application/json; charset=utf-8` requests/responses | C-RT-5 | written |
| V3-4 | Response timestamps RFC 3339 with explicit offset | C-FMT-1 | written |
| V3-5 | Unknown body fields ignored, never error; unknown query params ignored | C-IGN-1..2 | written |
| V3-6 | IDs opaque ≤64 chars incl. fixture ids | C-IGN-3 (65-char fixture id → error; ruling: 422) | written/ruling |

## V4 Model & fixtures (§4)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V4-1 | Restaurants/tables only via reset; no creation endpoints | C-API-0 | written |
| V4-2 | Restaurant fields: timezone/slot_minutes/reservation_duration_minutes/cancellation_cutoff_minutes/opening_hours; table capacity | fixture round-trip C-API-2 | written |
| V4-3 | weekday ∈ mon..sun; opens/closes HH:MM; closes>opens same day | invalid-fixture probes C-FX-1 | written/ruling |
| V4-4 | Seeded users log in immediately with given password | C-AU-0 | written |
| V4-5 | Seeded reservations: POST fields + id/reference/user_id | C-FX-2 | written |
| V4-6 | Any calendar date; past start not rejected per se; cutoff rules still apply | C-PST-1 | written |

## V5 Errors (§5)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V5-1 | Every 4xx/5xx body `{"error":{"code","message"}}` | asserted inside every error check | written |
| V5-2 | 400 malformed_request: unparseable body or wrong-JSON-type field | C-ERR-1..3 | written |
| V5-3 | 400 missing_idempotency_key: absent or empty | C-IDM-1a/b | written |
| V5-4 | 401 unauthenticated: missing/malformed/unknown bearer | C-AU-4 | written |
| V5-5 | 403 forbidden | probably unreachable in stage 1 | gap |
| V5-6 | 404 not_found: absent or not visible | C-PRM-* | written |
| V5-7 | 409 idempotency_key_reuse | C-IDM-3 | written |
| V5-8 | 422 validation_failed: missing field/param or unspecific rule | C-ERR-4.. | written |
| V5-9 | Correct type + invalid format/range → 422 (dates, negatives, over-max) | C-ERR-5..7 | written |
| V5-10 | Endpoint precedence: bad party_size (string/bool) & non-bare starts_at_local → 422 not 400 | C-ERR-8..10 | written |
| V5-11 | Integer query params plain digits: `1e9`/`4.0`/`+4` → 422 regardless of value | C-AV-6 | written |
| V5-12 | Idempotency-Key 1..255 chars else 422 | C-IDM-2 (0→400, 256→422, 255 ok) | written |
| V5-13 | No 5xx ever, incl. under load | global assert in every check + concurrency | written |

## V6 Auth (§6)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V6-1 | signup → 201 {user_id, display_name, token} | C-AU-1 | written |
| V6-2 | login → 200 same shape | C-AU-2 | written |
| V6-3 | duplicate email → 409 email_taken | C-AU-3 (+case ruling) | written/ruling |
| V6-4 | password <8 → 422; email not local@domain → 422 | C-AU-3b/c | written |
| V6-5 | login wrong pw or unknown email → 401 unauthenticated | C-AU-3d/e | written |
| V6-6 | Bearer required except /health, /_test/reset, /_test/export, /_test/import, /auth/*, 3 public GETs | C-AU-4 sweep | written |
| V6-7 | Tokens don't expire; multiple concurrent tokens/sessions | C-AU-5 | written |
| V6-8 | Passwords hashed (bcrypt/scrypt/Argon2-class), never plaintext | C-XP-7 export scan for plaintext | written |

## V7 Idempotency (§7)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V7-1 | Keys required on POST /reservations + POST /reservation-moves only | C-IDM-1 (both), cancel/PATCH need none | written |
| V7-2 | Key scoped to authenticated user; same key across users independent | C-IDM-4 | written |
| V7-3 | Replay = same user+method+path+body; same key other path = new request | C-IDM-5 | written |
| V7-4 | Order: parse → auth → idempotency BEFORE field validation/resource checks; used key + different invalid body → 409 | C-IDM-6 | written |
| V7-5 | absent/empty → 400 missing_idempotency_key | C-IDM-1 | written |
| V7-6 | first use → normal 201 | implicit | written |
| V7-7 | replay same body → 200, body identical as JSON value (order/space-insensitive) | C-IDM-7 (reordered keys) | written |
| V7-8 | same key different body → 409 | C-IDM-3 | written |
| V7-9 | key after 4xx failure = free (first use) | C-IDM-8 | written |
| V7-10 | concurrent identical: exactly one 201, others 200 same body, effect once | C-CON-1 | written |
| V7-11 | replay returns ORIGINAL response after change/cancel; no further state change | C-IDM-9 | written |
| V7-12 | "same body" = same JSON value post-parse | C-IDM-7 | written |

## V8 API (§8)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V8-1 | GET /restaurants public → {restaurants:[{id,name,timezone}]} | C-API-1 | written |
| V8-2 | GET /restaurants/{id} public, full fixture shape; 404 unknown | C-API-2/2b | written |
| V8-3 | GET /availability public; restaurant_id+date+party_size required → else 422 | C-AV-1 | written |
| V8-4 | Slot grid: every slot_minutes step from opens while slot+dur ≤ closes | C-AV-2 (boundary slot incl., next excl.) | written |
| V8-5 | available_table_ids: capacity ≥ party_size, no overlap, fixture order; empty allowed | C-AV-3..5 | written |
| V8-6 | closed day → slots []; tableless slot still listed | C-AV-7/5 | written |
| V8-7 | starts_at_local `YYYY-MM-DDTHH:MM` + starts_at correct offset | C-AV-2 | written |
| V8-8 | POST /reservations auth+key; body fields as spec | C-BK-1 | written |
| V8-9 | starts_at_local bare wall-clock resolved in restaurant tz | C-ERR-9/10, C-BK-1 | written |
| V8-10 | 201 body: reservation_id, reference, restaurant_id, table_id, party_size, status confirmed, starts_at_local, starts_at, ends_at, created_at | C-BK-1 | written |
| V8-11 | reference: 6–12 [A-Z0-9], globally unique, immutable | C-BK-2, C-PAT-4 | written |
| V8-12 | error codes: 409 table_unavailable; 422 not_on_slot_grid; 422 outside_opening_hours; 422 party_exceeds_capacity; 422 validation_failed (party<1/non-int); 422 invalid_local_time; 404 unknown restaurant/table/cross-restaurant table | C-BK-3..9 | written |
| V8-13 | GET /reservations: caller's only, starts_at desc, confirmed+cancelled, {"reservations":[...]}, empty shape | C-LST-1..3 | written |
| V8-14 | GET /reservations/{ref}: 404 if not caller's — no existence leak | C-PRM-1 | written |
| V8-15 | cancel → 200 {reference,status:cancelled,...}; frees table immediately (availability re-offers) | C-CXL-1..2 | written |
| V8-16 | double cancel → 200 current state | C-CXL-3 | written |
| V8-17 | within cutoff or later → 409 cutoff_passed; foreign → 404 | C-CXL-4..6 | written |
| V8-18 | PATCH subset of table_id/starts_at_local/party_size; no key needed | C-PAT-1 | written |
| V8-19 | PATCH validation identical to create; cutoff vs CURRENT start; cancelled → 409 reservation_cancelled; success releases old+reserves new atomically; failure leaves original | C-PAT-2..6 | written |
| V8-20 | reference + reservation_id survive amendment | C-PAT-4 | written |

## V9 Time & DST (§9)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V9-1 | local times follow restaurant tz incl. transitions; IANA offsets | C-DST-* | written |
| V9-2 | spring-forward gap: nonexistent locals absent from availability; booking → 422 invalid_local_time | C-DST-1 (Berlin 2026-03-29), C-DST-4 (NY 2026-03-08) | written |
| V9-3 | fall-back: ambiguous locals resolve to FIRST occurrence; slot listed once; second occurrence not bookable | C-DST-2 (Berlin 2026-10-25 → +02:00), C-DST-5 (NY 2026-11-01 → -04:00) | written |
| V9-4 | duration absolute: 90m from 01:30 fold night ends local 02:00 | C-DST-3 | written |
| V9-5 | both zones, all four 2026 transitions | covered above | written |

## V10 Export/import (§10)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V10-1 | GET /_test/export unauth → 200 {track:"tablekeeper",format_version:1,state:{...}} | C-XP-1 | written |
| V10-2 | POST /_test/import whole object → 204 atomic replace; accepts own export unchanged | C-XP-2 | written |
| V10-3 | no dependency on source process/files/volume/port | API-level covered; cross-container via harness isolated run | partial |
| V10-4 | repeat import restores without duplicating | C-XP-3 | written |
| V10-5 | invalid JSON → §5; missing fields/wrong track/version/invalid state → 422 WITHOUT changing destination | C-XP-4a..e | written |
| V10-6 | preserves accounts+hash login, live tokens, fixture config, reservations, references, ALL idempotent bodies+original responses; identities/statuses/timestamps not regenerated; failed keys still reusable | C-XP-5a..e | written |
| V10-7 | export atomic read-only snapshot; later writes don't change it | C-XP-6 | written |
| V10-8 | import removes ALL prior destination data/credentials; reset clears imported state | C-XP-8 | written |
| V10-9 | exports are private artifacts (tokens inside) — kept out of repo | process | n/a |

## V11 Atomic reservation moves (§11)

| Req | Clause | Checks | Status |
|---|---|---|---|
| V11-1 | POST /reservation-moves: auth + idempotency key | C-MV-1 | written |
| V11-2 | moves 1..8 objects, distinct string refs; bad shape/dupes → 422 | C-MV-2a..d | written |
| V11-3 | all bookings caller's + same restaurant; foreign → 404; mixed restaurants → 422; no token → 401 | C-MV-3..5 | written |
| V11-4 | items accept PATCH fields; omitted retain; unknown ignored | C-MV-6 | written |
| V11-5 | identity/owner/created_at never change | C-MV-7 | written |
| V11-6 | cancelled booking in batch → 409 reservation_cancelled | C-MV-8 | written |
| V11-7 | per-booking cutoff; non-occupancy errors in input order, cutoff first per booking; overlap among results or with unlisted → 409 table_unavailable; unchanged listed keep occupancy | C-MV-9..11 | written |
| V11-8 | all-or-nothing: occupancy, records, retry keys; 201 {"reservations":[...]} input order incl. unchanged | C-MV-12 (table swap), C-MV-13 | written |
| V11-9 | replay → original 200 even after later amendments/cancels | C-MV-14 | written |
| V11-10 | no-op moves retain values; export/import preserves batch receipts | C-MV-15, C-XP-5f | written |

## Cross-cutting

| Req | Clause | Checks |
|---|---|---|
| VX-1 | Conservation: a table held at most once at any instant | model.py M-OCC replay |
| VX-2 | reset determinism: identical fixture → identical observable state; no residue | C-RT-4 |
| VX-3 | cutoff boundary now == starts_at - cutoff → 409 (within-or-later) | C-CXL-4 (seeded near-boundary; jitter-safe) |

## Gaps & rulings needed (explicit — nothing implied)

- G-1 V1-4 clean-room: process property, not black-box checkable.
- G-2 V5-5 `forbidden`: likely unreachable in stage 1 (no role surface).
- G-3 `moves` wrong JSON type (e.g. string): §11 "invalid shape → 422" vs §5 wrong-type → 400. Either accepted; flagged.
- G-4 `GET /availability` unknown restaurant_id: check expects 404; would accept 422 pending ruling.
- G-5 Fixture validation strictness (bad weekday/HH:MM/closes≤opens/65-char ids): spec silent on reset failure; check expects 422 + unchanged state; other sane 4xx recorded as observation pending ruling.
- G-6 Email uniqueness case sensitivity: spec silent; exact-duplicate asserted, case variant recorded as observation.
- G-7 Exact cutoff equality not reachable to the ms black-box; covered by seeded inside/outside cases.
- G-8 V2-x deployment limits: verified via official harness + manual build in Phase 2.
- G-9 PATCH with zero recognized fields: spec silent; recorded as observation.
- G-10 `Idempotency-Key` whitespace-only: spec says absent/empty → 400; whitespace-only recorded as observation.
