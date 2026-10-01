# Requirements matrix — Tablekeeper stage 1

Source: official spec `tablekeeper/spec/stage-1.md` @ commit
`803560d2a678ace1414465c098eb0ab5380ffade` (D:\tk-official).
Every row is a testable clause. Rows marked RULING resolve a sentence that
could be read two ways; rulings choose the reading that keeps every stated
invariant true.

## S1 — Scope and correctness law

| # | Clause | Check idea |
|---|---|---|
| S1-1 | Two `confirmed` reservations never overlap on one table; interval is half-open `[starts_at, starts_at+duration)` | boundary: 19:00+90min vs 20:30 start does NOT overlap |
| S1-2 | Holds under up to 50 concurrent requests | 50 parallel identical bookings → exactly one confirmed |
| S1-3 | Retries/rejections create no duplicate or partial bookings | retry same key; rejected create frees nothing and leaves nothing |
| S1-4 | Clean-room: no external product source/schemas used | n/a process |

## S2 — Delivery / resource limits

| # | Clause | Check idea |
|---|---|---|
| S2-1 | Dockerfile + RUN.md; one command builds and starts; compose never read | build from clean clone via RUN.md |
| S2-2 | Runs with `-e PORT=<port>` + port mapping; default 8080; listens 0.0.0.0 | PORT=8123 honored |
| S2-3 | No outbound network at runtime; build-time fetch allowed | isolated harness mode |
| S2-4 | 2 vCPU / 2 GiB / 60s to first healthy / 5s per request (10s `/_test/reset`) | timing probes |
| S2-5 | Fonts/scripts/styles in image; no external runtime assets | isolated mode |

## S3 — Runtime contract

| # | Clause | Check idea |
|---|---|---|
| S3-1 | `GET /health` → 200 `{"status":"ok"}` once ready; non-200 allowed before ready | immediate + post-warmup |
| S3-2 | `POST /_test/reset` with fixture → 204; subsequent reads see ONLY that fixture; repeatable; no auth | reset→get; reset twice; residue check |
| S3-3 | `application/json; charset=utf-8` both directions | content-type check |
| S3-4 | Response timestamps RFC 3339 with explicit offset | regex `±HH:MM`, no `Z` requirement — offset may be `+00:00` |
| S3-5 | Unknown body fields ignored, never error; unknown query params ignored | extra fields 2xx |
| S3-6 | IDs opaque ≤64 chars, incl. fixture-supplied IDs | 65-char fixture id → error (see RULING R-1) |

## S4 — Model / fixtures

| # | Clause | Check idea |
|---|---|---|
| S4-1 | Restaurants+tables exist ONLY via `/_test/reset`; no creation endpoints | POST /restaurants → 404/405 (RULING R-2) |
| S4-2 | Restaurant fields: `timezone` (IANA), `slot_minutes`, `reservation_duration_minutes`, `cancellation_cutoff_minutes`, `opening_hours`; Table: `capacity` | fixture round-trip in GET /restaurants/{id} |
| S4-3 | `weekday` ∈ mon..sun; `opens`/`closes` `HH:MM` local; closes later same day; never crosses midnight | invalid weekday/HH:MM handling (R-3) |
| S4-4 | Seeded users log in immediately with given password | reset→login 200 |
| S4-5 | `reservations` may seed confirmed bookings: POST body fields + `id`, `reference`, `user_id` | seeded booking appears in owner's GET /reservations |
| S4-6 | Any calendar date; past starts allowed; cutoff rules still apply | book yesterday OK |

## S5 — Errors

| # | Clause | Check idea |
|---|---|---|
| S5-1 | Every 4xx/5xx body `{"error":{"code","message"}}`; message any wording | shape check on each error |
| S5-2 | 400 `malformed_request`: unparseable body OR wrong JSON type field | `not json`, `{"party_size":"x"}` on paths not excepted |
| S5-3 | 400 `missing_idempotency_key`: required header absent or empty | both |
| S5-4 | 401 `unauthenticated`: missing/malformed/unknown bearer | 3 variants |
| S5-5 | 403 `forbidden`: authenticated, not permitted | (stage-3 surface; stage-1 unlikely reachable) |
| S5-6 | 404 `not_found`: no such resource OR not visible to caller | other user's reservation → 404 not 403 |
| S5-7 | 409 `idempotency_key_reuse`: same user+key, different body | direct probe |
| S5-8 | 422 `validation_failed`: missing required field/param or rule violation with no more specific code | omitted fields |
| S5-9 | Correct-type field w/ invalid format/range → 422 (invalid dates, negatives, over-max) | `date=2026-13-40` |
| S5-10 | Endpoint-specific field rules take precedence: invalid `party_size` (incl. strings/booleans) and non-bare-local `starts_at_local` → 422 `validation_failed` (NOT malformed) | `party_size:"4"`, `party_size:true`, `starts_at_local:"2026-09-24 19:00"` |
| S5-11 | Integer query params are plain decimal digits: `1e9`, `4.0`, `+4` → 422 whatever the value | all three on party_size |
| S5-12 | `Idempotency-Key` length 1..255 else 422 `validation_failed` | 0 (→400 missing), 256 chars →422 |
| S5-13 | Requests never produce 5xx, including under load | fuzz + concurrency sweep |

## S6 — Auth

| # | Clause | Check idea |
|---|---|---|
| S6-1 | `POST /auth/signup` → 201 `{user_id, display_name, token}` | happy path |
| S6-2 | `POST /auth/login` → 200 same shape | happy path |
| S6-3 | Duplicate email → 409 `email_taken` | re-signup; case handling R-4 |
| S6-4 | Password <8 → 422; email not `local@domain` → 422 | `a@`, `a@b`, missing @, etc. |
| S6-5 | Wrong password or unknown email on login → 401 `unauthenticated` | both |
| S6-6 | Bearer required on everything except `/health`, `/_test/reset`, `/auth/*`, `GET /restaurants`, `GET /restaurants/{id}`, `GET /availability` | each endpoint sans token → 401 |
| S6-7 | Tokens don't expire; multiple concurrent tokens per account | two logins both work |
| S6-8 | Passwords stored via bcrypt/scrypt/Argon2-class hash; never plaintext | inspect export/state |

## S7 — Idempotency

| # | Clause | Check idea |
|---|---|---|
| S7-1 | Keys required on `POST /reservations`, `POST /reservation-moves` only | PATCH/cancel/series-less need none |
| S7-2 | Scoped to authenticated user; two users may share a key string | cross-user probe |
| S7-3 | Replay = same method+path+body for same user; same key different path is a NEW request (must succeed) | key on /reservations then /reservation-moves |
| S7-4 | Idempotency resolves AFTER JSON parse + auth, BEFORE field validation / current-resource checks | used key + invalid new body → 409 reuse not 422 |
| S7-5 | Header absent/empty → 400 `missing_idempotency_key` | both |
| S7-6 | First use → normal 201 | — |
| S7-7 | Replay same body → 200, body identical as JSON value (key order/whitespace irrelevant) | reorder keys in body |
| S7-8 | Same key different body → 409 `idempotency_key_reuse` | — |
| S7-9 | Key whose original request failed 4xx is free again (first use) | fail then retry same key w/ valid body → 201 |
| S7-10 | Concurrent identical requests, unused key: exactly one 201, rest 200 same body; effect once | 20-thread race |
| S7-11 | Replay returns ORIGINAL response even after resource changes/cancelled; no further state change | create→cancel→replay → 200 original confirmed body |
| S7-12 | RULING R-5: does a successful replay need the key returned 5xx? Spec: "failed with 4xx" frees key; 5xx must never happen (S5-13), so unreachable | — |

## S8 — API

| # | Clause | Check idea |
|---|---|---|
| S8-1 | `GET /restaurants` public → `{"restaurants":[{id,name,timezone}]}` | no token |
| S8-2 | `GET /restaurants/{id}` public → fixture shape incl. slot_minutes, durations, cutoff, opening_hours, tables; 404 unknown | compare fields |
| S8-3 | `GET /availability` public; restaurant_id+date+party_size all required else 422 | drop each param |
| S8-4 | Slot grid: every `slot_minutes` step from `opens` s.t. `slot+duration ≤ closes` | boundary slot at closes-duration included; +slot_minutes excluded |
| S8-5 | `available_table_ids`: capacity ≥ party_size, no overlapping confirmed, fixture order; empty allowed | ordering probe |
| S8-6 | Closed day → `"slots":[]`; slot with no tables still listed | closed weekday; all-taken slot |
| S8-7 | `starts_at_local` full `YYYY-MM-DDTHH:MM` + `starts_at` w/ correct offset | DST days |
| S8-8 | `POST /reservations`: requires auth+key; body restaurant_id/table_id/starts_at_local/party_size | — |
| S8-9 | `starts_at_local` bare wall-clock `YYYY-MM-DDTHH:MM`, resolved in restaurant tz; offset/Z suffix → 422 validation_failed (S5-10) | `+02:00` suffix rejected |
| S8-10 | 201 body fields: reservation_id, reference, restaurant_id, table_id, party_size, status confirmed, starts_at_local, starts_at, ends_at, created_at | field presence/types |
| S8-11 | `reference`: 6–12 chars [A-Z0-9], globally unique, immutable | regex + two bookings differ |
| S8-12 | Overlap → 409 `table_unavailable`; off-grid → 422 `not_on_slot_grid`; outside hours/end after closes → 422 `outside_opening_hours`; party>capacity → 422 `party_exceeds_capacity`; party<1 or non-int → 422 `validation_failed`; nonexistent local → 422 `invalid_local_time`; unknown restaurant/table/cross-restaurant table → 404 `not_found` | each case |
| S8-13 | RULING R-6: precedence among create validations — spec lists cases but no order; apply: auth→key→parse→idempotency→missing-field→type→field rules; restaurant/table existence before slot checks (404 sensible first); party_size type before grid checks | verifier probes ambiguous orderings |
| S8-14 | `GET /reservations` → caller's only, `starts_at` desc, confirmed+cancelled, `{"reservations":[...]}`; empty list shape | cross-user isolation |
| S8-15 | `GET /reservations/{reference}` → 404 if not caller's (no existence leak) | other user's ref |
| S8-16 | `POST /reservations/{ref}/cancel` → 200 `{reference,status:"cancelled",...}`; frees table immediately (availability re-offers slot) | cancel→availability |
| S8-17 | Double cancel → 200 current state (not error) | — |
| S8-18 | Within `cancellation_cutoff_minutes` of start or later → 409 `cutoff_passed`; not caller's → 404 | boundary: exactly at cutoff = passed? R-7 |
| S8-19 | `PATCH /reservations/{ref}`: subset of table_id/starts_at_local/party_size; NO idempotency key | each field combo |
| S8-20 | PATCH validation identical to POST; cutoff measured against CURRENT start; cancelled → 409 `reservation_cancelled`; successful amendment releases old + reserves new atomically; failed leaves original occupancy | patch to taken table → original intact |
| S8-21 | `reference`/`reservation_id` survive amendment | — |

## S9 — Time & DST

| # | Clause | Check idea |
|---|---|---|
| S9-1 | All local times in restaurant `timezone`; IANA rules | — |
| S9-2 | Spring-forward gap: nonexistent locals never in availability; booking → 422 `invalid_local_time` | Berlin 2026-03-29 02:30 |
| S9-3 | Fall-back: ambiguous locals resolve to FIRST occurrence (pre-transition); slot appears once; second occurrence not bookable | Berlin 2026-10-25 02:30 → +02:00 |
| S9-4 | Duration is absolute: 90min from 01:30 on fall-back night ends 02:00 local | Berlin case |
| S9-5 | Handle Europe/Berlin + America/New_York 2026 transitions | both zones' dates |

## S10 — Export/import

| # | Clause | Check idea |
|---|---|---|
| S10-1 | `GET /_test/export` unauth → 200 `{track:"tablekeeper", format_version:1, state:{...}}` | shape |
| S10-2 | `POST /_test/import` takes ENTIRE export object → 204; atomic replace; unchanged export accepted | roundtrip |
| S10-3 | No dependency on source process/files/volume/port/net | import in fresh container |
| S10-4 | Repeating import restores state without duplicating | import twice → same |
| S10-5 | Invalid JSON → §5 rules; missing fields/wrong track/version/invalid state → 422 `validation_failed` WITHOUT changing destination | state survives failed import |
| S10-6 | Preserves: accounts+hashed-password login, live bearer tokens, fixture config, reservations, references, ALL completed idempotent bodies+original responses; identities/statuses/timestamps not regenerated; failed keys remain reusable | login post-import; replay same key+body → 200 original |
| S10-7 | Export is atomic read-only snapshot; later source writes don't change it | export→mutate→diff export |
| S10-8 | Import removes ALL prior destination data/credentials; reset clears imported state too | import→old token dead; reset→empty |
| S10-9 | 10s timeout for test controls; restart survival not required | — |

## S11 — Atomic reservation moves

| # | Clause | Check idea |
|---|---|---|
| S11-1 | `POST /reservation-moves`: auth + idempotency key | 401/400 probes |
| S11-2 | `moves`: 1..8 objects, distinct string references; bad shape/dupes → 422 `validation_failed` | 0, 9, dup refs, non-array |
| S11-3 | Every booking caller's + same restaurant; unknown/foreign ref → 404; mixed restaurants → 422; no token → 401 | each |
| S11-4 | Items accept PATCH fields (table_id, starts_at_local, party_size); omitted retain; unknown fields ignored | partial moves |
| S11-5 | Identity/owner/created_at never change | — |
| S11-6 | Cancelled booking in batch → 409 `reservation_cancelled` | — |
| S11-7 | Per-booking cutoff applies; non-occupancy errors in input order, cutoff before other errors for that booking; overlaps among resulting or with unlisted → 409 `table_unavailable`; unchanged listed bookings keep occupancy | ordering probes |
| S11-8 | All-or-nothing: occupancy, records, retry keys; success 201 `{"reservations":[...]}` input order incl. unchanged | fail 2nd move → 1st unchanged + key free |
| S11-9 | Replay → original 200 response even after later amendments/cancels | — |
| S11-10 | No-op moves keep all values; export/import preserves batch receipts + bookings | — |

## Rulings

- **R-1** Fixture IDs >64 chars: the ≤64 limit "also applies to IDs supplied in
  reset fixtures" — a fixture violating it is invalid input. Ruling: reset with
  an over-length id → 422 `validation_failed` (defensible; also accept treating
  whole fixture as state). Implementer: reject with 422.
- **R-2** `POST /restaurants` etc. don't exist → route absent → 404 `not_found`
  is fine; method/route both unknown. Any 4xx acceptable; prefer 404.
- **R-3** Invalid fixture fields (bad weekday, malformed HH:MM, closes ≤ opens):
  reset body is caller input → 422 `validation_failed`, state unchanged.
- **R-4** Email uniqueness: compare case-insensitively on the domain part and
  local part (email convention); store as supplied. `Ada@x.com` vs `ada@x.com`
  → `email_taken`. Chosen for safety: real systems treat mailbox names
  case-insensitively; a hidden check either way is defensible, conservative
  reading wins.
- **R-5** Idempotent original returning 5xx: unreachable because 5xx is
  forbidden; treat any non-2xx original as failed (key reusable).
- **R-6** Create-validation order (beyond spec-mandated
  parse→auth→idempotency→validation): rule order = missing fields → field
  type/format → restaurant existence (404) → table existence/membership (404)
  → party_size rules → slot-grid → opening-hours → local-time existence →
  capacity → occupancy. Where a hidden check disagrees, single-cause bodies
  still produce the right code.
- **R-7** Cutoff boundary: "within `cancellation_cutoff_minutes` of
  `starts_at`, or later" — cancel allowed iff `now < starts_at - cutoff`.
  Exactly at the boundary is "within" → 409.
- **R-8** `created_at` uses UTC `+00:00` offset per example; any explicit
  offset is legal, but emit UTC for determinism.
- **R-9** Availability `date` validity: non-`YYYY-MM-DD` or impossible date →
  422 `validation_failed`; restaurant closed that weekday → slots `[]`.
- **R-10** `party_size` query param: digits only (S5-11); `0` or negative →
  422 `validation_failed` (in-range rule violation); huge values → also 422
  (no capacity can match → still must be 422 not crash).
- **R-11** `reservation-moves` `moves[i]` extra fields ignored; a move naming
  zero patchable fields is a legal no-op move.
- **R-12** `PATCH` on another caller's reference → 404 (same as GET/cancel —
  no existence leak anywhere).

## Conservation law (stage 1)

Seat-occupancy: for every table and instant, at most one confirmed reservation
covers it. Asserted after every concurrency check. Money-analog: references
unique globally; idempotency keys map 1:1 to first-use outcome.
