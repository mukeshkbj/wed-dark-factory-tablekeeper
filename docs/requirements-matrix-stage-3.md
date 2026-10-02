# Requirements matrix — Tablekeeper stage 3

Source: official spec `tablekeeper/spec/stage-3.md` @ commit
`803560d2a678ace1414465c098eb0ab5380ffade` (D:\tk-official).
**All stage-1 and stage-2 rows continue to apply unchanged.** Every row below
is a testable stage-3 clause. Rows marked RULING resolve a sentence that could
be read two ways; rulings choose the reading that keeps every stated invariant
true.

## E — Availability explanations

| # | Clause | Check idea |
|---|---|---|
| E-1 | `GET /availability` accepts optional `explain=true`; every other value, including `false`, `1`, empty, or repeated/ambiguous use, is 422 `validation_failed` | value sweep |
| E-2 | Without `explain`, response keeps the stage-2 shape: no `explain` field appears | regression diff |
| E-3 | With `explain=true`, every slot carries `explain` | shape check |
| E-4 | Every restaurant table appears exactly once in `explain`, available or not, in fixture order | full-table ordering |
| E-5 | Every explanation reports `table_id`, `policy_version`, `available`, and `rules` | field presence |
| E-6 | `rules` reports `capacity` then `no_overlap` for every table; a rule that holds is true; a table failing both reports both false | matrix of capacity/occupancy failures |
| E-7 | `available` is true exactly when both rules hold | truth-table probe |
| E-8 | Tables with `available=true` are exactly `available_table_ids`, same order | set+order equality |
| E-9 | Closed day still returns `{"slots":[]}`; an open slot with no available table still appears with a full `explain` entry per table | closed-day + all-taken slot |
| E-10 | Published policies can change slot values, capacities, grid, hours and therefore explanations | pre/post-policy availability |
| E-11 | `policy_version` identifies the policy selected for that slot's local start date (policy 0 = fixture) | dated-policy probe |

## H — Reservation history and decision

| # | Clause | Check idea |
|---|---|---|
| H-1 | `GET /reservations/{reference}/history` returns the reservation's own record, oldest first | create/patch/cancel flow |
| H-2 | Only the owner may read history; another user or no token gets the same 404 `not_found` as a foreign/nonexistent reservation | owner/foreign/anonymous probes |
| H-3 | Cancelled reservations retain readable history | cancel → history |
| H-4 | `seq` starts at 1 and increments by exactly 1; entries are returned in `seq` order, also `at` order | rapid writes in same second |
| H-5 | `created` names `table_id`, `starts_at_local`, `party_size`, each `from:null` | create event shape |
| H-6 | `changed` names only fields that actually changed, ordered `table_id`, `starts_at_local`, `party_size` | multi-field patch |
| H-7 | A PATCH that sets every field to its current value succeeds but records no history entry and increments nothing | no-op patch |
| H-8 | `cancelled` carries `changes: []`, and no event follows it | cancel terminality |
| H-9 | Replaying an idempotent create records nothing new | replay → history unchanged |
| H-10 | Every history entry carries the reservation's resulting `revision` and complete `accepted_terms`; old entries never acquire newer terms | terms snapshot diff |
| H-11 | `GET /reservations/{reference}/decision` returns `{reference, revision, accepted_terms}` for the current booking, including after cancellation | decision endpoint |
| H-12 | History and decision return 404 even without authentication; this is the explicit exception to stage-1's general 401 rule | anonymous probe |

## P — Booking policies

| # | Clause | Check idea |
|---|---|---|
| P-1 | Fixture restaurants may declare `manager_user_ids`; absent defaults to `[]` | fixture default |
| P-2 | Only listed manager users may `POST /restaurants/{id}/policies`; authenticated non-manager → 403 `forbidden`; no token → 401; unknown restaurant → 404 | auth matrix |
| P-3 | Managers do not gain access to other diners' private lookup/history/series | manager foreign-read probe |
| P-4 | Policy publish requires an idempotency key and follows stage-1 replay/reuse rules | key required/replay/reuse |
| P-5 | Body is a complete policy, not a patch; all required fields must be present | omitted-field sweep |
| P-6 | `effective_from` is an actual `YYYY-MM-DD` date | invalid date cases |
| P-7 | `slot_minutes` and `reservation_duration_minutes` are integers 1..1440; `cancellation_cutoff_minutes` integer 0..10080; booleans are not integers | boundary/type sweep |
| P-8 | `opening_hours` follows stage-1 validation and contains no duplicate weekdays | duplicate weekday probe |
| P-9 | `capacities` names exactly the restaurant's table ids, each integer 1..100 | missing/extra/invalid capacity |
| P-10 | Policies cannot change table ids, labels, timezone, or declared combinations | shape/invariant review |
| P-11 | Unknown fields are ignored | extra-field probe |
| P-12 | Invalid policy is 422 `validation_failed` with no state change and no allocated version | invalid publish then list/decision |
| P-13 | Successful publish returns 201 with supplied policy plus integer `policy_version`; versions start at 1 and increase once per restaurant | publish two policies |
| P-14 | Failed writes and replays allocate no version | fail/replay then list |
| P-15 | Policies are immutable; no update/delete path changes them | direct/API review |
| P-16 | Publication order may differ from effective-date order; policy selection chooses greatest `effective_from` not later than booking's local start date, ties by greatest `policy_version` | out-of-order effective dates |
| P-17 | Effective dates may be in the past; publication never retroactively edits an accepted booking | past-effective policy |
| P-18 | `GET /restaurants/{id}/policies` is public and returns `{"policies":[...]}` in publication order, omitting policy 0 | anonymous GET ordering |
| P-19 | Ordinary restaurant detail still returns original fixture configuration; availability/booking decisions use the selected policy | detail vs decision divergence |
| P-20 | Successful policy publication increments restaurant revision once; failures/no-ops/replays do not | internal/export invariant |

## T — Accepted terms, revisions, and amendments

| # | Clause | Check idea |
|---|---|---|
| T-1 | Every reservation response gains `revision` and `accepted_terms` | create/get/list/patch/cancel views |
| T-2 | `revision` is 1 at creation; seeded bookings start at revision 1 under policy 0 | seed and create probes |
| T-3 | `accepted_terms` snapshots the entire selected policy excluding `effective_from`: `policy_version`, `slot_minutes`, `reservation_duration_minutes`, `cancellation_cutoff_minutes`, `opening_hours`, `capacities` | exact shape |
| T-4 | Existing bookings keep original terms, end times and history when policies publish | publish after booking |
| T-5 | Old idempotent create responses remain original responses, including original revision and terms | replay after later policy/amend |
| T-6 | Cancel checks the booking's accepted cutoff against the current start | pre/post-policy cancel |
| T-7 | Cancel increments reservation revision once; repeated cancel does not | double-cancel revision/history |
| T-8 | A real amendment checks the old accepted cutoff first, then validates all resulting fields against the policy applicable to the resulting start date | cutoff-vs-policy ordering probe |
| T-9 | A real amendment atomically replaces accepted terms and end time and increments revision once | policy-crossing amend |
| T-10 | A no-op amendment retains terms, end time, revision and history, but still requires a confirmed editable booking | no-op on confirmed/cancelled/cutoff |
| T-11 | Failed amendments change nothing: terms, end, revision, history, occupancy | failing amend probe |
| T-12 | `expected_revision` is optional; a positive integer differing from current revision gives 409 `stale_revision` before cutoff or field validation | stale + invalid body |
| T-13 | Invalid `expected_revision` type or range gives 422 `validation_failed`; booleans are invalid | type sweep |
| T-14 | Two concurrent amendments using one revision: at most one real change succeeds | race probe |
| T-15 | Unknown fields on PATCH remain ignored | unknown-field probe |

## S — Recurring series

| # | Clause | Check idea |
|---|---|---|
| S-1 | `POST /series` requires auth and idempotency key; body accepts `anchor_reference`, `count`, `interval_weeks` | auth/key/body probes |
| S-2 | Anchor must belong to caller, be confirmed, and satisfy its accepted cancellation cutoff | owner/foreign/cancelled/cutoff |
| S-3 | Unknown or foreign anchor → 404 `not_found`; cancelled → 409 `reservation_cancelled`; already adopted → 409 `already_in_series`; no token → 401 | error matrix |
| S-4 | `count` is integer 2..12 including anchor; `interval_weeks` integer 1..4; booleans and non-integers → 422 | boundary sweep |
| S-5 | Occurrence 0 is the anchor itself: reference, identity, revision, terms, history, timestamps and original idempotent response unchanged | create series → anchor diff |
| S-6 | Occurrence `i` starts on anchor local date + `i * interval_weeks * 7` days at same local clock time | weekly/biweekly dates |
| S-7 | Each generated occurrence independently selects its date's policy, including duration and capacity, and obeys opening, DST and occupancy rules | policy boundary series |
| S-8 | Nonexistent local time rejects the entire adoption with 422 `invalid_local_time`; repeated local times use stage-1 first-occurrence rule | DST gap/fold |
| S-9 | Generated occurrences use anchor party size and table selection, including canonical `table_ids` for pairs | pair series probe |
| S-10 | Adoption is atomic: no partial series, reservations, histories, counters or idempotency claim survive failure | fail mid-series then inspect/retry |
| S-11 | First failing occurrence in index order determines the ordinary booking error | controlled occurrence failure |
| S-12 | Success returns 201 `{series_id, revision:1, interval_weeks, occurrences:[...]}` with all `count` occurrences in index order | shape/count/order |
| S-13 | Each generated occurrence has a distinct ordinary reservation reference; references and indices never change when dates/tables change | later PATCH probe |
| S-14 | Occurrences appear in ordinary reservation lists, occupy their tables, and have ordinary histories | list/availability/history |
| S-15 | `GET /series/{series_id}` returns the same shape with current reservation states; only owner may read — another user or no token gets 404 | owner/foreign/anonymous |
| S-16 | A real individual PATCH permanently marks that occurrence `exception:true` and increments series revision once | patch occurrence |
| S-17 | A no-op or failed individual PATCH changes neither exception nor series revision | no-op/failure |
| S-18 | Cancelling an occurrence increments series revision once, retains the cancelled occurrence, and does not mark exception; repeated cancel does nothing | cancel occurrence |
| S-19 | Cancelling the anchor does not cancel siblings | anchor cancel probe |
| S-20 | Ordinary cutoff and reservation revision checks still apply to occurrence writes | cutoff/stale revision |
| S-21 | Adoption increments restaurant revision once for the whole operation | internal/export invariant |
| S-22 | Series replay returns the original series response even after later changes and changes no counters | replay after patch/cancel |
| S-23 | Unknown fields are ignored | extra-field probe |
| S-24 | `series_id` is an opaque id within the stage-1 id limits | length/opacity check |

## X — Upgrade and import continuity

| # | Clause | Check idea |
|---|---|---|
| X-1 | Stage-3 accepts exports produced by the same team's stage-1 or stage-2 service | both export shapes import |
| X-2 | Adoption works on reservations imported from stage-1 or stage-2 | import → `POST /series` |
| X-3 | Existing confirmation links, sessions and original booking retries remain valid after import | lookup/token/idempotent replay |
| X-4 | Imported reservations lacking stage-3 fields are normalised to revision 1 and policy-0 accepted terms | import → history/decision |
| X-5 | Import remains atomic: policies, series, histories, revisions, idempotency and occupancy swap together | failed import leaves state |
| X-6 | Stage-3 export round-trips without losing policies, series membership, exceptions, histories, revisions or accepted terms | export → import → compare |

## B — Combined-table policy/history integration

| # | Clause | Check idea |
|---|---|---|
| B-1 | Accepted terms apply to combinations; capacity is the sum of the selected policy's member capacities | policy changes capacity for pair |
| B-2 | Single-to-single history retains `table_id`; pair creation uses `table_ids` with `from:null` instead of `table_id` | pair create history |
| B-3 | Any change involving a pair uses `table_ids` complete before/after lists | single↔pair and pair↔pair |
| B-4 | Table-set order in history/responses is the declared combination order | reversed request canonicalisation |
| B-5 | A reversed input pair names the same set and is not by itself an amendment, history entry, revision bump, or series exception | reversed-pair no-op |
| B-6 | Policy selection, revision, idempotent replay and occupancy rules apply unchanged to pair bookings | pair regression sweep |

## M — Collective moves under policies and series

| # | Clause | Check idea |
|---|---|---|
| M-1 | Each real change in `POST /reservation-moves` uses individual PATCH semantics: old accepted cutoff first, then resulting-date policy | policy-crossing move |
| M-2 | Per-move `expected_revision` is optional and follows PATCH validation/stale rules | stale one item fails batch |
| M-3 | A no-op move retains terms, revision and history but may be returned unchanged in the response | no-op move |
| M-4 | All resulting bookings must satisfy amendment and occupancy rules; failure leaves every booking unchanged | atomic failure probe |
| M-5 | Every changed booking gains one reservation revision and one `changed` history entry | history per moved item |
| M-6 | Restaurant revision increases once for the whole successful batch | internal/export invariant |
| M-7 | Each affected series revision increases once, and each changed series occurrence becomes a permanent exception | move series occurrence |
| M-8 | Failed batches and replays change no revisions, histories or exception flags | replay after later edits |

## D — Dispatch-derived delivery clauses

| # | Clause | Check idea |
|---|---|---|
| D-1 | `stage-3/` is a complete independently buildable service: Dockerfile, RUN.md, source, tests, inherited UI, no symlinks/submodules/nested `.git` | clean-clone build |
| D-2 | Stage-3 begins as a verbatim copy of frozen stage-2 (`5be5343` product tree) before feature commits | first scaffold commit diff |
| D-3 | Hardened deployment mode still disables `/_test`; judge image keeps it enabled by default | `TK_HARDENED` probe |
| D-4 | Runtime zero outbound network including UI assets; no runtime dependency fetch | isolated run + asset audit |
| D-5 | Existing stage-2 browser surface continues to satisfy its matrix; stage-3 spec explicitly requires no new screens for explanations or history | inherited UI suite |
| D-6 | Message budget discipline: one phase-ready notice and one verdict/handoff per seat; no status chatter | room process |

## Rulings (stage 3)

- **R3-1** `explain` describes individual tables only. It does not add
  combination rows; pair availability remains represented by stage-2
  `available_options`. With `explain=true`, `available_options` is still
  present and uses the selected policy's capacities/duration/hours.
- **R3-2** `manager_user_ids` fixture field: optional list of existing user
  ids. Absent → `[]`; equivalent duplicates collapse to first occurrence.
  Non-list, non-string, over-length, or unknown user ids are invalid fixture
  content → 422 `validation_failed`, state unchanged. This extends the R-16
  coherence floor: a manager id that cannot name a seeded user is incoherent.
- **R3-3** Policy version allocation belongs to the write's successful first
  execution only. A replayed publish returns the original response with 200 and
  does not allocate another version; a same-key different body is
  `idempotency_key_reuse`.
- **R3-4** `expected_revision` names the reservation revision, not the series
  revision or restaurant revision. A mismatch is checked before cutoff and
  field validation; `0`, negatives, booleans, floats and strings are 422.
- **R3-5** No-op amendment detection for `table_ids` uses the canonical set in
  declared `combinable` order. A reversed pair equivalent to the current set is
  the same value and therefore a no-op.
- **R3-6** History field naming: singles use `table_id`; any reservation whose
  before or after set is a pair uses `table_ids` with complete canonical lists.
  Do not emit both fields in one change entry.
- **R3-7** Series generated occurrences preserve the anchor's canonical
  `table_ids` selection. For a pair, occupancy must hold for every member, and
  capacity is the sum under the occurrence's selected policy.
- **R3-8** `GET /series/{id}` occurrences expose current reservation state;
  `exception:false` remains the anchor/default state until a real diner PATCH,
  collective move, or later-stage operation permanently marks it.
- **R3-9** `POST /restaurants/{id}/policies` and `POST /series` are new
  idempotent write paths. They join the same per-user key namespace by
  method+path+body: same key on a different path is a different request.
- **R3-10** History and decision authenticate only by ownership outcome: no
  token, bad token, foreign owner, and unknown reference all produce 404
  `not_found`, not 401/403, because the spec explicitly grants that exception.
- **R3-11** `restaurant_revision` starts at 0 on reset/import baseline and is
  internal state even if no stage-3 endpoint exposes it. It increments once per
  successful booking create, real amendment, cancellation, policy publication,
  series adoption, or successful move batch; no-ops/failures/replays do not.
- **R3-12** For cancellation and stale-revision checks, `current start` and
  `current revision` mean the booking's stored pre-write values, not values
  from the incoming body.
- **R3-13** `accepted_terms.capacities` contains the selected policy's complete
  capacity map for every table id, including non-booked members; pair capacity
  is derived by summing that map.
- **R3-14** A policy's `opening_hours` must be a complete replacement schedule;
  absent weekdays mean closed for decisions under that policy.
- **R3-15** Stage-3 adds no required browser screens or testids. Existing
  stage-2 UI may keep rendering slots without explanation/history affordances;
  adding optional affordances must not break inherited selectors or flows.
- **R3-16** `POST /series` validates semantic errors in occurrence-index order
  after anchor/body/auth checks. For ordinary booking failures inside generated
  occurrences, return that occurrence's normal error unchanged.
- **R3-17** Generated series occurrences receive fresh reservation ids and
  references at adoption time; only the anchor keeps its original identifiers.
- **R3-18** If a policy makes an existing booking's table smaller than its
  party, the existing booking remains valid; the new capacity affects only new
  availability/booking/amendment decisions.
- **R3-19** A move batch's restaurant/series revision increments happen once
  per successful batch, not once per item. An all-no-op batch is a successful
  non-real write and does not increment them.
- **R3-20** Export compatibility normalises older reservations to revision 1
  and policy-0 accepted terms on import; their histories may be reconstructed
  minimally as a single `created` event unless richer history was exported.

## Conservation law (stage 3, extends stage-2)

Seat-occupancy per table still holds under policies and series. Policy history,
reservation revision/history, series membership/exception state, restaurant
revision, and idempotency records are atomic with each successful write. No
failed write, replay, preview-like read, import failure, or partial series may
leak state.
