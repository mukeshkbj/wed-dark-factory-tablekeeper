# Requirements matrix — Tablekeeper (all four stages)

Coordinator artifact. Every numbered row is a checkable clause from the official
specs (`D:\tk-official\tablekeeper\spec\stage-N.md`, kit commit `803560d`).
Row ids are stable: `S<stage>-<section>.<n>`. Rulings on ambiguous sentences are
recorded at the end; the spec text wins over taste. The deep stage-1 numbering
used in the stage-1 dispatches lives in `docs/requirements-matrix-stage-1.md`;
this file is the whole-run map.

## Stage 1 — reservations API

### Delivery & deployment (§2)

| Id | Requirement |
|---|---|
| S1-2.1 | HTTP service + `Dockerfile` + `RUN.md`; one build/start command, no manual setup |
| S1-2.2 | Image runs standalone with `-e PORT=<port>` + port mapping; no Compose dependence |
| S1-2.3 | Runtime limits: 2 vCPU, 2 GiB, healthy ≤60 s, 50 concurrent, 5 s/req (10 s reset), zero outbound net at runtime, ephemeral disk OK |
| S1-2.4 | All runtime assets (fonts, scripts, styles) inside the image; no external services |

### Runtime contract (§3)

| Id | Requirement |
|---|---|
| S1-3.1 | Listen `0.0.0.0:$PORT`, default 8080 |
| S1-3.2 | `GET /health` → 200 `{"status":"ok"}` once ready; non-200 allowed before ready |
| S1-3.3 | `POST /_test/reset` takes fixture body, replaces ALL state → 204; repeated resets OK; unauthenticated; enabled in delivered image |
| S1-3.4 | `application/json; charset=utf-8` both ways; response timestamps RFC 3339 with explicit offset |
| S1-3.5 | Unknown body fields ignored, never error; unknown query params ignored |
| S1-3.6 | IDs opaque strings ≤64 chars, format ours; applies to fixture-supplied ids too |

### Model & fixtures (§4)

| Id | Requirement |
|---|---|
| S1-4.1 | Restaurants/tables only via `/_test/reset`; no creation endpoints |
| S1-4.2 | Restaurant fields: `timezone` (IANA), `slot_minutes`, `reservation_duration_minutes`, `cancellation_cutoff_minutes`, `opening_hours` per weekday, `capacity` per table |
| S1-4.3 | `weekday` ∈ mon..sun; `opens`/`closes` `HH:MM`; closes later same day, never crosses midnight |
| S1-4.4 | Seeded users log in with given password immediately |
| S1-4.5 | Seeded `reservations` = confirmed bookings, fields of POST body + `id`, `reference`, `user_id` |
| S1-4.6 | Any calendar date valid; past starts not rejected solely for being past (cutoff rules still apply) |

### Errors (§5)

| Id | Requirement |
|---|---|
| S1-5.1 | Every 4xx/5xx body: `{"error":{"code":..., "message":...}}` |
| S1-5.2 | 400 `malformed_request` = unparseable body OR wrong JSON type |
| S1-5.3 | 400 `missing_idempotency_key` = required header absent/empty |
| S1-5.4 | 401 `unauthenticated` = missing/malformed/unknown bearer |
| S1-5.5 | 403 `forbidden` = authenticated but not permitted |
| S1-5.6 | 404 `not_found` = no such resource OR not visible to caller |
| S1-5.7 | 409 `idempotency_key_reuse` = same key, different body, same user |
| S1-5.8 | 422 `validation_failed` = missing required field/param, or rule violated with no more specific code |
| S1-5.9 | Correct type + invalid format/range → 422 `validation_failed` (bad dates, negatives, over-max) |
| S1-5.10 | `party_size` strings/booleans → 422 `validation_failed` (not 400); non-bare-local `starts_at_local` → 422 |
| S1-5.11 | Integer query params: plain decimal digits only; `1e9`, `4.0`, `+4` → 422 regardless of value |
| S1-5.12 | `Idempotency-Key` 1..255 chars else 422 |
| S1-5.13 | No 5xx ever, including under concurrent load |

### Auth (§6)

| Id | Requirement |
|---|---|
| S1-6.1 | `POST /auth/signup` → 201 `{user_id, display_name, token}` |
| S1-6.2 | `POST /auth/login` → 200 same shape |
| S1-6.3 | Duplicate email → 409 `email_taken`; password <8 → 422; email not `local@domain` → 422; wrong password/unknown email → 401 |
| S1-6.4 | Bearer required everywhere except `/health`, `/_test/*`, signup/login, `GET /restaurants`, `GET /restaurants/{id}`, `GET /availability` |
| S1-6.5 | Tokens never expire; multiple valid tokens/concurrent sessions per account |
| S1-6.6 | Passwords hashed (bcrypt/scrypt/Argon2 or equivalent); no plaintext |

### Idempotency (§7)

| Id | Requirement |
|---|---|
| S1-7.1 | Required on `POST /reservations`, `POST /reservation-moves` only (stage-1 surface) |
| S1-7.2 | Key scoped per authenticated user; same string across users independent |
| S1-7.3 | Replay = same user + same method + same path + same parsed JSON body; same key+body on different path is a different request |
| S1-7.4 | Ordering: body parses as JSON object → caller authenticated → idempotency resolved → field validation/resource checks. Used-key+new-body = 409 even if new body invalid |
| S1-7.5 | First use → 201 normal; replay → 200 + original body (JSON-equal); different body → 409; key after 4xx failure → treated as first use |
| S1-7.6 | "Same body" = equal parsed JSON value (key order/whitespace irrelevant) |
| S1-7.7 | Concurrent identical requests on unused key: exactly one 201, rest 200 same body, effect once |
| S1-7.8 | Replay returns original response even after resource changes/cancel; no further state change |

### API surface (§8)

| Id | Requirement |
|---|---|
| S1-8.1 | `GET /restaurants` public → `{restaurants:[{id,name,timezone}]}` |
| S1-8.2 | `GET /restaurants/{id}` public → fixture shape incl slot/duration/cutoff/opening_hours/tables; 404 unknown |
| S1-8.3 | `GET /availability` public; params restaurant_id+date+party_size all required (missing → 422) |
| S1-8.4 | Slot every `slot_minutes` from `opens` where `slot+duration ≤ closes`; closed day → `slots: []` |
| S1-8.5 | `available_table_ids`: capacity ≥ party_size, no overlapping confirmed reservation, fixture order; empty slot still listed |
| S1-8.6 | Response slots carry `starts_at_local` (`YYYY-MM-DDTHH:MM`, feeds POST unchanged) and `starts_at` (RFC3339 offset) |
| S1-8.7 | `POST /reservations`: 201 `{reservation_id, reference, restaurant_id, table_id, party_size, status:"confirmed", starts_at_local, starts_at, ends_at, created_at}` |
| S1-8.8 | `reference` 6–12 chars `[A-Z0-9]`, globally unique, immutable |
| S1-8.9 | Errors: overlap→409 `table_unavailable`; off-grid→422 `not_on_slot_grid`; outside hours/end after closes→422 `outside_opening_hours`; party>capacity→422 `party_exceeds_capacity`; party<1/non-int→422 `validation_failed`; nonexistent local time→422 `invalid_local_time`; unknown restaurant/table/wrong-restaurant table→404 |
| S1-8.10 | `GET /reservations` → caller's, `starts_at` desc, confirmed+cancelled, create-response shape; empty → `{"reservations":[]}` |
| S1-8.11 | `GET /reservations/{ref}` → 404 if not caller's (no existence leak) |
| S1-8.12 | `POST /reservations/{ref}/cancel` → 200 `{status:"cancelled",...}`; frees table immediately (next availability offers slot); already cancelled → 200 current state; within cutoff or later → 409 `cutoff_passed`; not caller's → 404 |
| S1-8.13 | `PATCH /reservations/{ref}`: any subset of table_id/starts_at_local/party_size; no idem key; identical validation to POST; cutoff vs CURRENT start → 409 `cutoff_passed`; cancelled → 409 `reservation_cancelled`; success releases old slot + reserves new atomically; failure leaves everything unchanged; `reference`/`reservation_id` survive |

### Time & DST (§9)

| Id | Requirement |
|---|---|
| S1-9.1 | All local times in restaurant `timezone` incl DST |
| S1-9.2 | Spring-forward gap times never appear in availability; booking one → 422 `invalid_local_time` |
| S1-9.3 | Fall-back repeated times resolve to FIRST occurrence; slot appears once; second occurrence unbookable |
| S1-9.4 | `reservation_duration_minutes` is absolute: 01:30+90min on fall-back night → local `ends_at` 02:00 not 03:00 |
| S1-9.5 | Correct IANA offsets per zone+date (Berlin 2026-03-29 / 2026-10-25; New_York 2026-03-08 / 2026-11-01 transitions named) |

### Export/import (§10)

| Id | Requirement |
|---|---|
| S1-10.1 | `GET /_test/export` → 200 `{track:"tablekeeper", format_version:1, state:{opaque}}`; `POST /_test/import` accepts entire object → 204; unauthenticated |
| S1-10.2 | Import atomically replaces ALL state; repeatable without duplication; no dependency on source process/files/port/network |
| S1-10.3 | Invalid JSON → §5; missing fields/wrong track/version/invalid state → 422 `validation_failed`, destination unchanged |
| S1-10.4 | Preserves: accounts+hashed passwords, live bearer tokens, fixture config, reservations, references, completed idempotent bodies+original responses; identities/statuses/timestamps never regenerated; failed request keys stay reusable |
| S1-10.5 | Import wipes previous destination data+credentials; reset still clears imported state; export is atomic read-only snapshot (later source writes don't change it) |

### Atomic moves (§11)

| Id | Requirement |
|---|---|
| S1-11.1 | `POST /reservation-moves`: auth + idem key; body `{moves:[{reference, table_id?|starts_at_local?|party_size?}]}` |
| S1-11.2 | `moves` 1..8 objects, distinct refs; bad shape/dup refs → 422 |
| S1-11.3 | Every booking caller's + same restaurant; unknown/other-owner → 404; mixed restaurants → 422; no token → 401 |
| S1-11.4 | Per item = PATCH fields; omitted fields retain; unknown fields ignored; identity/owner/created_at never change |
| S1-11.5 | Cancelled booking → 409 `reservation_cancelled`; per-booking cutoff applies; non-occupancy errors take precedence in INPUT ORDER, cutoff before other checks per booking |
| S1-11.6 | Overlap among resulting bookings or with unlisted booking → 409 `table_unavailable`; unchanged listed bookings retain occupancy |
| S1-11.7 | All-or-nothing: occupancy, records, retry keys; success → 201 `{reservations:[...]}` input order incl unchanged |
| S1-11.8 | Replay → 200 original even after later amendments/cancels; no-op moves keep all values; export/import preserves batch receipts |

## Stage 2 — browser UI + combined tables (extends §1)

| Id | Requirement |
|---|---|
| S2-1 | Routes `/`, `/signup`, `/login`, `/lookup` return HTML; other screens reachable via UI; SSR or CSR allowed |
| S2-2 | Out-of-order search: later-started search's results win; stale response never restores old results (grid, labels, form describe latest) |
| S2-3 | 409 `table_unavailable` on submit → `booking-error` + availability refresh, form+inputs preserved, no confirmation |
| S2-4 | Lost booking response (incl after commit) → nonempty `booking-uncertain`, no error/no confirmation; unchanged form retries SAME idem key + body; successful retry clears uncertainty and shows ORIGINAL reference; confirmed rejection → `booking-error` |
| S2-5 | All recovery rules apply to combinations; no polling/live-update/cross-tab/reload recovery required; server authoritative, never fabricate success from cache |
| S2-6 | All listed `data-testid` hooks present (signup-*, login-*, auth-error, current-user, logout-button, restaurant-select, date-input, party-size-input, search-button, availability-grid, slot-*, no-slots, booking-*, confirmation*, lookup-*, reservation-*) |
| S2-7 | Warm hospitality product feel; visual hierarchy; human restaurant/table labels prominent; consistent type/spacing/color system; distinct states (available/unavailable/selected/loading/success/refused/uncertain) |
| S2-8 | Usable at 375px + desktop, no horizontal scroll; visible labels, apparent focus, sufficient contrast; considered empty/loading/error states; consistent nav |
| S2-9 | Auth screens: `auth-error` only when error; `current-user` shows display name on every screen when signed in; `logout-button` |
| S2-10 | Grid: cell `slot-{table_id}-{HH:MM}` carries `data-available` true iff table in that slot's `available_table_ids`; click available → booking form; click unavailable → nothing; signed-out click → `auth-error` or redirect `/login` |
| S2-11 | Booking form: `booking-summary` = table label + local start; `booking-party-size` prefilled; stays on screen after success; identical resubmit → same `confirmation-reference`, no error, no new booking; changed field → new request; retries per §7 |
| S2-12 | Confirmation: `confirmation`, `confirmation-reference` (exactly the reference), `confirmation-details` (restaurant name + table label + local start) |
| S2-13 | Lookup: `reservation-detail` on found; `reservation-status` exactly `confirmed`/`cancelled`; `reservation-cancel-button` absent once cancelled; `reservation-error` on not-found or refused cancel |
| S2-14 | Upgrade: accept stage-1 export; pre-import session stays signed in; retained reference works in lookup; lost-response booking retryable post-import with same body/key → original confirmation; applies between requests |
| S2-15 | `combinable`: unordered PAIRS only, non-transitive, capacity = sum; seeded reservations may carry `table_ids`; `status` cancelled honored |
| S2-16 | `GET /availability` slots gain `available_options`: every single + declared pair with summed capacity ≥ party_size and no overlap on any member; singles fixture order then pairs `combinable` order; pair `table_ids` in combinable order; `available_table_ids` unchanged (singles only) |
| S2-17 | `POST /reservations` takes `table_ids`; `table_id` still accepted = set of one; both → 422 `validation_failed`; responses always carry `table_ids`, plus `table_id` only when set size 1 |
| S2-18 | Pair not declared or >2 tables → 422 `combination_not_allowed`; any member overlapping → 409 `table_unavailable`; party>summed capacity → 422 `party_exceeds_capacity`; dup id → 422 `validation_failed` |
| S2-19 | `PATCH` accepts `table_ids` same rules; cancel frees every table; moves accept `table_ids` per move; no overlapping resulting bookings |
| S2-20 | UI combination cells `slot-{t_a}+{t_b}-{HH:MM}` (combinable order) with `data-available`; `confirmation-tables`/`reservation-tables` contain every table label; `booking-summary` names every table |
| S2-21 | Concurrency: results equal to some serial order; rules hold at every read |

## Stage 3 — policies, history, series (extends §§1–2)

| Id | Requirement |
|---|---|
| S3-1 | `explain=true` (only accepted value; `false`/`1`/empty → 422): every slot carries `explain` per table — every restaurant table exactly once, fixture order; both rules (`capacity`, `no_overlap`) reported in order; `available` iff both hold and matches `available_table_ids` order; without param, stage-1 shape unchanged |
| S3-2 | `GET /reservations/{ref}/history` owner-only (404 otherwise, even unauthenticated — overrides general 401); cancelled reservation keeps history; `seq` 1..n +1; order = `at` order; `created` lists all 3 fields from null; `changed` only actual changes in field order table_id→starts_at_local→party_size; same-value PATCH = success + NO entry; `cancelled` empty changes, nothing follows; idempotent replay records nothing |
| S3-3 | `manager_user_ids` in fixture (default []); only managers publish policies; unknown restaurant 404; non-manager 403; no token 401; managers get no access to other diners' private data |
| S3-4 | `POST /restaurants/{id}/policies` idempotent write; COMPLETE policy not patch → 201 + `policy_version` (1..n per restaurant, +1 each); failed writes/replays allocate none; policy 0 = fixture rules pre-publication; immutable |
| S3-5 | Policy selection: for booking's local start date, greatest `effective_from` ≤ date; ties → greatest version; same-date new policy supersedes for future decisions only; past effective dates allowed; never retroactive |
| S3-6 | All policy fields required; `effective_from` real date; grid/duration int 1..1440; cutoff int 0..10080; booleans not ints; opening_hours stage-1 rules, no dup weekdays; `capacities` exactly the table ids, int 1..100; invalid → 422 no version/state change; table ids/labels/timezone/combinations immutable by policy; unknown fields ignored |
| S3-7 | `GET /restaurants/{id}/policies` public, publication order, omits policy 0; restaurant detail still returns fixture config; decisions use selected policy; `explain` entries carry `policy_version` |
| S3-8 | Every reservation response gains `revision` (1 at create) + `accepted_terms` (full selected policy minus `effective_from`); seeded bookings rev 1 policy 0; old-key replays return original rev/terms |
| S3-9 | Publication never changes existing bookings/end times/history; cancel checks ACCEPTED cutoff vs current start; real amendment checks old accepted cutoff then validates ALL resulting fields against resulting-date policy, atomically replacing terms+end, rev +1; no-op keeps terms/rev/history but still needs confirmed editable booking; failed amend changes nothing; cancel +1 rev, repeat cancel no |
| S3-10 | `PATCH` optional `expected_revision`: positive int, mismatch → 409 `stale_revision` BEFORE cutoff/validation; bad type/range → 422; omitted → stage-1 semantics; concurrent same-revision amends: ≤1 real change |
| S3-11 | Each history entry carries resulting `revision` + full `accepted_terms`; old entries never gain newer terms; `GET /reservations/{ref}/decision` → `{reference, revision, accepted_terms}` current incl cancelled; same owner-only 404 |
| S3-12 | `POST /series`: idempotent; `{anchor_reference, count 2..12 incl anchor, interval_weeks 1..4}`; anchor caller-owned + confirmed + cutoff satisfied; unknown/foreign → 404; cancelled → 409 `reservation_cancelled`; already adopted → 409 `already_in_series`; bad values incl booleans → 422; no token → 401 |
| S3-13 | Occurrence 0 = anchor unchanged (reference/identity/revision/terms/history/timestamps/original response); occurrence i = anchor local date + i×interval_weeks×7 days, same local clock; each picks its own date's policy (duration/capacity) + normal opening/DST/occupancy; nonexistent local time rejects WHOLE adoption `invalid_local_time`; repeated → first-occurrence rule; anchor's party size + table set; fully atomic; first failing occurrence in index order sets the error |
| S3-14 | 201 `{series_id, revision:1, interval_weeks, occurrences:[{index, reference, exception:false, reservation}]}` all count in index order; distinct ordinary references; refs/indices immutable across date/table changes; occurrences in normal lists, occupy tables, normal histories |
| S3-15 | `GET /series/{id}` owner-only 404 otherwise |
| S3-16 | Real individual PATCH on occurrence → `exception:true` permanent + series rev +1; no-op/failure → neither; cancel → series rev +1, keeps occurrence, NOT exception; repeat cancel nothing; anchor cancel doesn't cascade; normal cutoff/revision apply; adoption = restaurant rev +1 once; replays return original, change no counter |
| S3-17 | Accepts stage-1/2 exports; adoption works on imported reservations; links/sessions/retries stay valid |
| S3-18 | Combined tables under policies: capacity = sum of SELECTED policy capacities; history uses `table_ids` (complete before/after) instead of `table_id` for pair ops; creation of pair = `table_ids` from null; set order = declared combinable order; reversed input pair = same set, not an amendment |
| S3-19 | Moves under policies: each real change = individual PATCH semantics (old cutoff, then resulting-date policy); per-move `expected_revision` optional; no-op keeps terms/history; all-or-nothing; each changed booking rev+history entry; restaurant rev +1 once; each affected series rev +1 and changed occurrences become permanent exceptions; failed/replay changes nothing |

## Stage 4 — closure replans + series amendments (extends all)

| Id | Requirement |
|---|---|
| S4-1 | `POST /restaurants/{id}/replans`: manager + idem key; `{table_id, from, to}` RFC3339 with offsets, `from < to`; bad interval → 422; unknown table → 404 |
| S4-2 | Closure = half-open `[from,to)`; considered = every confirmed booking at restaurant overlapping; others keep assignments |
| S4-3 | Planning bounds: ≤6 tables, ≤4 declared pairs, ≤6 considered bookings; larger MAY → 422 `planning_limit` |
| S4-4 | Each considered booking keeps reference/owner/party/start/end/accepted terms; assigned single or declared pair with capacity under ITS OWN accepted terms; no conflicts with fixed bookings, other assignments, prior applied closures, or proposed closure; cutoffs don't block operator repair; no booking dropped/cancelled |
| S4-5 | Minimize lexicographically: (1) count of bookings whose table set changes; (2) total unused seats (capacity−party_size) over considered; (3) option-rank vector ascending by reference, ranks = singles fixture order then pairs declared order from 0 |
| S4-6 | 201 `{plan_id, restaurant_revision, closure{...}, assignments[{reference, table_ids, changed}] (all considered, reference order), moved_count, unused_seats}`; preview stores plan only — no closure/occupancy/revision/history changes; infeasible → 409 `no_feasible_plan`, nothing changes |
| S4-7 | Restaurant revision: 0 after reset; +1 per successful new booking, real amendment, cancellation, policy publication, plan application; never for no-ops/failures/previews/replays |
| S4-8 | `POST /restaurants/{id}/replans/{plan_id}/apply` body `{}`, manager + idem key → 201 `{plan_id, restaurant_revision, reservations[all considered, ref order]}`; unknown/foreign plan → 404; intervening restaurant revision → 409 `stale_plan`; already-applied under different key → 409 `plan_already_applied`; replay same key → 200 original even after later changes; atomic |
| S4-9 | Apply records closure + assignments together; moved booking rev +1 + `reassigned` history entry with `table_ids` change + `plan_id`, terms/times identical; unmoved gain nothing; restaurant rev +1 once for whole plan |
| S4-10 | Applied closures exclude singles+pairs from availability and reject creates/amends → 409 `table_unavailable`; `explain.no_overlap` false for closure as for conflicting booking |
| S4-11 | Concurrent applications never partially move bookings; closure at another restaurant doesn't invalidate plan |
| S4-12 | `POST /series/{id}/amend`: owner-only idempotent; unknown/foreign → 404; no token → 401; `{expected_revision: pos int, from_index: int 0..count-1, local_time: HH:MM 00:00..23:59}`; booleans invalid ints; bad input → 422; revision mismatch → 409 `stale_revision` before any cutoff/booking validation; unknown fields ignored |
| S4-13 | Amend indices ≥ from_index, excluding cancelled + exception occurrences; change clock time on original scheduled local dates; keep reference/owner/party/current table set; identical-resulting = no-op keeps terms; each real change: old accepted cutoff then resulting-date policy (PATCH-like) |
| S4-14 | Resulting occurrences must not conflict with unchanged occurrences, other bookings, applied closures; failure → histories/idem records/revisions all unchanged; non-occupancy errors in index order; else `table_unavailable` |
| S4-15 | Success → 201 current series response; each changed occurrence +1 rev + `changed` entry; series + restaurant rev +1 once each if anything changed; no exceptions marked; all-no-op/empty set → success, no revision change; replay → 200 original |
| S4-16 | Replans may move series occurrences preserving exception flags, scheduled dates, identities, terms; affected series rev +1 per application if ≥1 member moved; concurrent amends from same expected_revision: ≤1 real change |
| S4-17 | Stage-4 accepts exports from stages 1–3 incl moved/cancelled occurrences; earlier receipts/histories/retries valid |

## Rulings (ambiguity resolutions recorded by coordinator)

- **R1 — Check ordering on writes:** body JSON-parse → auth(401) → idempotency resolution
  (missing key 400, reuse 409) → shape/type validation (400/422) → resource existence
  (404) → domain rules. `stale_revision`/`stale_plan` precede cutoff and field
  validation where spec says so (S3-10, S4-12). Per-booking cutoff precedes other
  checks inside `reservation-moves` (S1-11.5); cross-booking precedence = input order.
- **R2 — `starts_at_local` error split:** malformed string or wrong type → 422
  `validation_failed`; well-formed but nonexistent local time (spring-forward) → 422
  `invalid_local_time`; exists but not a `slot_minutes` step from `opens` →
  `not_on_slot_grid`; on grid but `[start, start+duration)` not within `[opens, closes]`
  → `outside_opening_hours`. Order: existence → grid → hours.
- **R3 — Grid membership vs hours:** "on the slot grid" means a `slot_minutes` multiple
  offset from `opens`; a time before `opens` that is nevertheless a clean multiple is
  `outside_opening_hours`, not `not_on_slot_grid`.
- **R4 — Cancel idempotence:** already-cancelled returns 200 regardless of cutoff —
  the already-cancelled row precedes `cutoff_passed`.
- **R5 — Idempotency storage:** only successful operations store a receipt; any 4xx
  leaves the key free. 5xx must never occur. Receipts persist through export/import.
- **R6 — Query-param integers:** `^[0-9]+$` only; sign/exponent/decimal all 422.
  `party_size=0` parses then fails range → 422 `validation_failed` either way.
- **R7 — PATCH no-op:** succeeds, changes nothing, no history entry (S3-3 refines:
  still requires confirmed + editable). Same-value-only PATCH = no-op.
- **R8 — Concurrency model:** single-writer critical section (or equivalent
  serializable transaction) around check-and-act on occupancy, idempotency keys,
  revisions — mandate invariant: check-and-act is one critical section.
- **R9 — Export snapshot:** export captures a consistent point-in-time snapshot; import
  installs it atomically (swap, not merge). `format_version`/`track` mismatch → 422
  with destination untouched.
- **R10 — `ends_at`:** absolute duration added to resolved `starts_at` instant; local
  rendering may show a surprising local end on transition nights (spec worked example).
- **R11 — restaurant revision vs reservation revision:** independent counters; batch
  operations bump restaurant revision once per request, reservation/series revisions
  once per actually-changed entity.
- **R12 — fixture `reference` charset:** fixture-supplied references are opaque IDs
  (any non-empty ≤64-char string, stored verbatim); the generated-reference charset
  (6-12 chars A-Z0-9) binds service-minted references only. Under verifier review.

## Invariants to enforce at the gate (mandate §invariants)

- **Conservation law:** two confirmed reservations never share a table over
  overlapping `[starts_at, starts_at+duration)` — one reusable assertion run after
  every concurrency check.
- **Chokepoints:** slot computation, occupancy check, idempotency resolution,
  revision increments each live in exactly one function all write paths share.
- **Exact quantities:** `unused_seats`, capacities, durations — integer arithmetic
  only, no floats anywhere in domain math.
