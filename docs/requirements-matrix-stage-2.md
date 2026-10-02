# Requirements matrix — Tablekeeper stage 2

Source: official spec `tablekeeper/spec/stage-2.md` @ commit
`803560d2a678ace1414465c098eb0ab5380ffade` (D:\tk-official).
**All stage-1 rows (S1..S11) in `requirements-matrix-stage-1.md` continue to
apply unchanged.** Every row below is a testable stage-2 clause. Rows marked
RULING resolve a sentence that could be read two ways; rulings choose the
reading that keeps every stated invariant true.

## U1 — Routes and rendering

| # | Clause | Check idea |
|---|---|---|
| U1-1 | `/`, `/signup`, `/login`, `/lookup` reachable by URL | direct GET each → HTML |
| U1-2 | Other screens reachable through the UI | nav traversal |
| U1-3 | Screen routes return HTML; §3.4 json convention is API-only | content-type text/html |
| U1-4 | SSR or CSR both permitted | n/a |

## U2 — Competing clients / uncertain outcomes

| # | Clause | Check idea |
|---|---|---|
| U2-1 | Search A starts before B, finishes after: grid/labels/form describe B; late response must NOT restore A | delayed-A race probe |
| U2-2 | Table taken after form opens → `409 table_unavailable` → `booking-error` shown + availability refreshed; selected form and inputs preserved; NO confirmation for that attempt | API-thief between open and submit |
| U2-3 | Booking response lost (incl. after commit) → nonempty `booking-uncertain`, NO `booking-error`, NO new confirmation | dropped-response probe |
| U2-4 | Unchanged form retries with SAME idempotency key and body; successful retry removes uncertain/error elements, shows ORIGINAL reference | retry → same reference |
| U2-5 | Confirmed rejection on retry → `booking-error` | 409/422 retry |
| U2-6 | Rules apply to combination bookings equally | combo retry probe |
| U2-7 | No background polling / live updates / cross-tab sync / reload recovery required; server authoritative; browser must not fabricate success from cache | design review |

## U3 — Product / visual direction

| # | Clause | Check idea |
|---|---|---|
| U3-1 | Coherent presentation-ready hospitality product, not a test harness; warm confident character | visual review |
| U3-2 | Obvious visual hierarchy; scannable dates/times/party/table choices; combined tables read as intentional seating, not concatenated ids | visual review |
| U3-3 | Consistent visual system (type, spacing, colour, controls, feedback); identifiable primary actions | visual review |
| U3-4 | Available / unavailable / selected / loading / success / refused / uncertain states visually distinct | state sweep |
| U3-5 | Human-readable restaurant + table labels prominent; technical ids only where helpful | label check |
| U3-6 | Clear and usable at 375 CSS px and desktop widths, no horizontal page scroll | viewport probes |
| U3-7 | Visible input labels; apparent keyboard focus; sufficient contrast; considered empty/loading/error states; consistent nav | a11y sweep |

## U4 — Signup / login testids

| # | Clause | Check idea |
|---|---|---|
| U4-1 | `signup-email`, `signup-password`, `signup-display-name` inputs; `signup-submit` button | selector presence |
| U4-2 | `login-email`, `login-password`, `login-submit` | selector presence |
| U4-3 | `auth-error` present ONLY when there is an error | absent on fresh /login |
| U4-4 | `current-user` on EVERY screen when signed in; text contains display name | all 4 routes |
| U4-5 | `logout-button` button; logout removes session UI | click → current-user detached |

## U5 — Search / availability grid (`/`)

| # | Clause | Check idea |
|---|---|---|
| U5-1 | `restaurant-select` (option values = restaurant ids), `date-input` (`YYYY-MM-DD`), `party-size-input` (number), `search-button`, `availability-grid`, `no-slots` | selectors |
| U5-2 | `slot-{table_id}-{HH:MM}` one cell per table per slot, e.g. `slot-t_2-19:00` | every table×slot |
| U5-3 | `no-slots` shown INSTEAD of grid when day has no slots | closed weekday |
| U5-4 | Cell `data-available="true"` iff its table_id ∈ slot `available_table_ids` FOR THE SEARCHED party size; else `"false"` | party 6 vs 2 sweep |
| U5-5 | Click available cell → booking form for that table+slot; click unavailable → nothing (no form) | force-click probe |
| U5-6 | Signed-out click on available cell → `auth-error` OR navigate to `/login` | either accepted |

## U6 — Booking form

| # | Clause | Check idea |
|---|---|---|
| U6-1 | `booking-form`, `booking-summary` (contains table label + local start), `booking-party-size` (number, pre-filled from search), `booking-submit`, `booking-error` | selectors + content |
| U6-2 | Form stays on screen after success | post-confirm DOM |
| U6-3 | Resubmit unchanged → same `confirmation-reference`, no `booking-error`, no second booking | double-submit → 1 reservation |
| U6-4 | Changing any field → next submission is a NEW booking request (new idempotency key) | edit → 409/refused distinct |
| U6-5 | Retries follow §7 (replay semantics) | same key+body |

## U7 — Confirmation

| # | Clause | Check idea |
|---|---|---|
| U7-1 | `confirmation` container after success | selector |
| U7-2 | `confirmation-reference` text is EXACTLY the reference, no surrounding words | `[A-Z0-9]{6,12}` fullmatch |
| U7-3 | `confirmation-details` contains restaurant name + table label + local start | substring check |

## U8 — Lookup (`/lookup`)

| # | Clause | Check idea |
|---|---|---|
| U8-1 | `lookup-reference-input`, `lookup-submit` | selectors |
| U8-2 | `reservation-detail` shown when found | selector |
| U8-3 | `reservation-status` text exactly `confirmed` or `cancelled` | exact match |
| U8-4 | `reservation-cancel-button` cancels; ABSENT once cancelled | detach probe |
| U8-5 | `reservation-error` on not-found OR refused cancel (e.g. cutoff) | ZZZZZZ + cutoff probe |

## U9 — Upgrade: existing clients after stage-1 export

| # | Clause | Check idea |
|---|---|---|
| U9-1 | Stage-2 service accepts an export produced by the same team's stage-1 service | s1 export → s2 import 204 |
| U9-2 | Browser signed in before upgrade stays signed in after (token survives import) | login → export s1 → import s2 → authed call |
| U9-3 | Retained booking reference still works through lookup | pre-upgrade ref resolves |
| U9-4 | Booking whose response was lost pre-export remains retryable post-import with same body+key → original confirmation recovered | in-flight-loss probe |
| U9-5 | Applies when import completes between browser requests; in-flight migration not required; no reload/new screen required; form + pending retry identity survive upgrade | scope note |

## C1 — Combined tables: model

| # | Clause | Check idea |
|---|---|---|
| C1-1 | Fixture gains `combinable`: list of unordered PAIRS of table ids in that restaurant — never 3+ | `["t_1","t_2"]` entry |
| C1-2 | Unlisted pair cannot be combined regardless of sizes | undeclared pair → 422 |
| C1-3 | Not transitive: `[t_1,t_2]`+`[t_2,t_3]` do NOT make `{t_1,t_3}` bookable | chain probe |
| C1-4 | Combination capacity = sum of member capacities | 2+4 seats party of 6 |
| C1-5 | Combo booking occupies BOTH tables for full duration | member avail drops |
| C1-6 | Seeded `reservations`: `confirmed` unless `status:"cancelled"`; may hold `table_id` OR `table_ids` | both seed shapes |
| C1-7 | Existing single-table request formats remain supported | `table_id` still works |

## C2 — `GET /availability`

| # | Clause | Check idea |
|---|---|---|
| C2-1 | Slots gain `available_options`; `available_table_ids` unchanged (singles only) | shape + regression |
| C2-2 | `available_options` = every single table AND every declared pair with `capacity >= party_size` and no overlapping confirmed reservation on ANY member | pair where member taken excluded |
| C2-3 | Ordering: singles first in fixture order, then pairs in `combinable` order | order assertion |
| C2-4 | `table_ids` within a pair emitted in `combinable` order | `["t_1","t_2"]` not reversed |
| C2-5 | Pair members individually too small still form a valid pair option when sum fits | party 6 on 2+4 |
| C2-6 | Option entries: `{ "table_ids": [...], "capacity": n }` | field shape |

## C3 — `POST /reservations` with `table_ids`

| # | Clause | Check idea |
|---|---|---|
| C3-1 | Body takes `table_ids` instead of `table_id`; `table_id` still accepted (= set of one) | both forms 201 |
| C3-2 | Both `table_id` and `table_ids` in one body → 422 `validation_failed` | dual-field probe |
| C3-3 | Responses ALWAYS carry `table_ids`; carry `table_id` ONLY when set has exactly one member | pair omits table_id |
| C3-4 | Pair not in `combinable` → 422 `combination_not_allowed` | undeclared pair |
| C3-5 | >2 tables → 422 `combination_not_allowed` | 3 ids |
| C3-6 | Any member taken for overlapping interval → 409 `table_unavailable` | book t_1, then pair t_1+t_2 |
| C3-7 | `party_size` > summed capacity → 422 `party_exceeds_capacity` | party 7 on 2+4 |
| C3-8 | Duplicate table id in set → 422 `validation_failed` | `["t_1","t_1"]` |
| C3-9 | All stage-1 error cases/precedence unchanged for single-table bodies | inherited suite |

## C4 — PATCH / moves / cancel with sets

| # | Clause | Check idea |
|---|---|---|
| C4-1 | `PATCH` accepts `table_ids` under same rules; both fields → 422 | patch to pair |
| C4-2 | Cancelling frees EVERY table in the set | combo cancel → both free |
| C4-3 | `reservation-moves` items accept `table_ids` per move | move to pair |
| C4-4 | No table may belong to overlapping resulting bookings | move collisions 409 |
| C4-5 | Browser recovery + original-receipt rules apply to combos (replay returns original `table_ids` body) | cancel→replay original |

## C5 — UI combinations

| # | Clause | Check idea |
|---|---|---|
| C5-1 | `slot-{t_a}+{t_b}-{HH:MM}` cells when a declared pair is available for searched party size; ids in `combinable` order; `data-available` like single cells | `slot-t_1+t_2-19:00` |
| C5-2 | `confirmation-tables` text contains EVERY table label | pair labels |
| C5-3 | `reservation-tables` on lookup — same | pair labels |
| C5-4 | `booking-summary` names EVERY table in selection | summary contains both labels |
| C5-5 | Single-table booking cell testid/confirmation/lookup unchanged | regression |

## C6 — Concurrency

| # | Clause | Check idea |
|---|---|---|
| C6-1 | Concurrent requests linearizable; requirements hold at every read | 50-way race on pair+members |

## D — Dispatch-derived (not spec text, still binding)

| # | Clause | Check idea |
|---|---|---|
| D-1 | Hardened deployment mode disables all `/_test` controls for public demos; judge image keeps them enabled by default; document the difference | `TK_HARDENED`-style env → 404s |
| D-2 | Demo seed: attractive built-in data, no external services; includes combinable pair(s) so combined seating shows in UI | seed review |
| D-3 | `stage-2/` complete + independently buildable: Dockerfile, RUN.md, source, tests, offline assets; no symlinks/submodules/nested .git | clean-clone build |
| D-4 | Runtime zero outbound network incl. UI assets — no CDN fonts/scripts/styles | isolated run + asset audit |

## Rulings (stage 2)

- **R2-1** `table_ids: []` (empty set): 422 `validation_failed`. The spec's
  "more than two tables → combination_not_allowed" does not cover zero; the
  generic missing/invalid-field rule does.
- **R2-2** `table_ids` with one element = a set of one: accepted whenever
  `table_id` would be; response then carries BOTH `table_ids:[t]` and
  `table_id:t` (|set|==1 rule).
- **R2-3** Unknown / foreign-restaurant table inside `table_ids` → 404
  `not_found` (inherited existence rule applies per member; a set is valid
  only if every member is).
- **R2-4** `combinable` fixture validation (extends R-3/G-5 floor): must be a
  list of 2-element arrays of two DISTINCT existing table ids of that
  restaurant. Violations → 422 `validation_failed`, state unchanged.
  Duplicate equivalent pairs (`[a,b]` twice, or `[a,b]`+`[b,a]`) are legal
  idempotent config — collapse to one; the pair's declared order is the FIRST
  occurrence's order. Absent `combinable` field = empty list.
- **R2-5** Combination cells are rendered ONLY when the pair is in that
  slot's `available_options` (capacity fits AND both members free). The spec
  says cells are "shown when a declared pair is available for the searched
  party size" — absent otherwise, not rendered with `data-available=false`.
  When rendered it carries `data-available="true"`; the attribute is emitted
  regardless so tests read it uniformly. FALLBACK if hidden checks demand a
  `false` cell: render declared pairs in every slot with availability flag.
- **R2-6** Response `table_ids` for a pair is canonicalised to `combinable`
  declaration order, whatever order the request used (`[t_2,t_1]` ≡ declared
  `[t_1,t_2]` — unordered pair is the same pair).
- **R2-7** Internal storage: reservation holds `table_ids` list (canonical
  order). Stage-1-imported state (`table_id` scalar) is normalised on import
  to `[table_id]`. `GET`/`PATCH`/cancel/moves views emit `table_ids` always,
  `table_id` iff singleton.
- **R2-8** A seeded `reservations[]` entry with `table_ids` must name a
  combinable pair of that restaurant (same coherence floor as R-16): an
  undeclared pair in a seed → 422 `validation_failed`. Seeded single entries
  keep `table_id` or `table_ids:[t]`.
- **R2-9** Lost-response retry rule (U2-4) binds to `POST /reservations`
  only — the spec scopes `booking-uncertain` to booking submission. Cancel
  refusal shows `reservation-error`; a lost cancel response is unspecified —
  retry-with-same-effect is safe (double cancel → 200 current state), no
  extra UI element required.
- **R2-10** `available_options` key is present on every slot (empty list
  allowed) — spec example shows it per-slot; uniform presence is the least
  surprising reading.
- **R2-11** `PATCH`/`moves` with BOTH `table_id` and `table_ids` → 422
  `validation_failed` (same rule as POST; the dual-field ban is about the
  field pair, not the endpoint).
- **R2-12** `party_size` smaller than each member's capacity can still book
  the declared pair — spec imposes no "must fill a single table first" rule;
  do not add one (dispatch: no restrictions contradicting the contract).
- **R2-13** Idempotency replay body includes the ORIGINAL `table_ids`
  response verbatim — replay-after-amendment returns the stale original,
  per §7.
- **R2-14** Combo cells: the `{HH:MM}` in the testid is the slot's local
  start `HH:MM` (same format as single cells).
- **R2-15** `auth-error` OR `/login` redirect on signed-out cell click:
  choose ONE — we direct to `/login` if simpler; either is contract. Decide
  in implementation, keep consistent.

## Conservation law (stage 2, extends stage-1)

Seat-occupancy per TABLE still holds: for every table and instant, at most
one confirmed reservation covers it — whether reached via single or pair
bookings. Combined bookings count once per member. Additional invariant:
a `table_ids` set is stored canonically; references stay globally unique;
idempotency keys map 1:1 to first-use outcome.
