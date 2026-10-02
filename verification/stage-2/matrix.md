# Stage-2 coverage matrix — tk-verifier (spec-derived)

Derived from the verbatim spec text (`s2-spec-partA.md` = stage-2.md;
`s2-spec-partB/C.md` = stage-1.md, fully inherited). Every testable clause →
a `W-*` requirement → check ids. Check prefixes: `C-*`/`M-*` = inherited
stage-1 suite (`verification/stage-1/checks.py`, `model.py`, imported
verbatim); `C2-*` = new API checks; `U-*` = `ui_checks.py`; `UPG-*` =
`upgrade_checks.py`. Status: `written` | `pending` (needs implementation)
| `gap` (not black-box checkable) | `obs` (spec ambiguous — asserted
loosely or recorded as observation).

## W-R Routes (stage-2 §Routes)

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-R-1 | `/`, `/signup`, `/login`, `/lookup` reachable by URL | U-RT:*, C2-RT:* | written |
| W-R-2 | Other screens reachable through UI | U-RT-nav | written |
| W-R-3 | Screen routes return HTML (§3.4 json is API-only) | content-type asserts | written |

## W-U Competing clients / uncertain outcomes

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-U-1 | Search A before B, finishes after: grid+labels+form describe B; late response never restores A | U-OOO-1/2 | written |
| W-U-2 | Table taken after form opens → 409 → `booking-error` + availability refresh; form+inputs preserved; NO confirmation | U-THF-1..6 | written |
| W-U-3 | Lost booking response (incl. post-commit) → nonempty `booking-uncertain`, no `booking-error`, no new confirmation | U-DRP-1/1b/2 | written |
| W-U-4 | Unchanged form retries SAME key+body; success clears uncertain/error + shows ORIGINAL reference; confirmed rejection → `booking-error` | U-DRP-3/4/5, U-BK-9 | written |
| W-U-5 | Same rules for combination bookings | U-DRP on combo path + C2-IDMC-* | written |
| W-U-6 | No polling/live-sync/reload-recovery required; server authoritative; no fabricated success | design review | gap |

## W-V Product / visual direction

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-V-1 | Coherent hospitality product, visual hierarchy, combined tables read as intentional seating | screenshots + visual review | obs |
| W-V-2 | Consistent visual system; distinct available/unavailable/selected/loading/success/refused/uncertain states | screenshots per state | obs |
| W-V-3 | Human-readable labels prominent; ids only where helpful | U-BK-2/6, U-CMB-3/5, U-LKP-4 (label asserts) | written |
| W-V-4 | Usable at 375 CSS px + desktop, no horizontal page scroll | U-VP:* | written |
| W-V-5 | Visible labels, apparent focus, contrast, empty/loading/error states, consistent nav | partially (labels via testids; focus/contrast manual) | obs |

## W-A Signup / login

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-A-1 | signup inputs+submit testids | U-TID:signup-* | written |
| W-A-2 | login inputs+submit testids | U-TID:login-* | written |
| W-A-3 | `auth-error` present only when an error exists | U-TID absent-check, U-AU-4 | written |
| W-A-4 | `current-user` on every screen when signed in; contains display name | U-AU-1/2/* | written |
| W-A-5 | `logout-button`; logout removes session UI | U-AU-3 | written |

## W-G Search / availability grid (`/`)

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-G-1 | testids: restaurant-select/date-input/party-size-input/search-button/availability-grid/no-slots | U-TID:*, U-GRID-1/5 | written |
| W-G-2 | `restaurant-select` option values are restaurant ids | U-GRID flow uses select_option by id | written |
| W-G-3 | `slot-{table_id}-{HH:MM}` one cell per table per slot | U-GRID-2/4 (count = tables×slots) | written |
| W-G-4 | cell `data-available` true iff table_id ∈ slot's `available_table_ids` for searched party size | U-GRID-2/3 cross-check vs API | written |
| W-G-5 | click available → booking form for that table+slot | U-BK-1/2 | written |
| W-G-6 | click unavailable → nothing | U-CELL-3 | written |
| W-G-7 | signed-out click → `auth-error` OR navigate `/login` (either is contract) | U-CELL-1 | written |
| W-G-8 | `no-slots` INSTEAD of grid when day has no slots | U-GRID-5 | written |

## W-B Booking form

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-B-1 | testids: booking-form/booking-summary/booking-party-size/booking-submit/booking-error | U-BK-* | written |
| W-B-2 | summary contains table label + local start | U-BK-2 | written |
| W-B-3 | party-size pre-filled from search | U-BK-3 | written |
| W-B-4 | form stays on screen after success | U-BK-7 | written |
| W-B-5 | unchanged resubmit → same reference, no error, no second booking | U-BK-8 (+API count) | written |
| W-B-6 | changed field → new booking request | U-BK-9/9b | written |
| W-B-7 | retries follow §7 | U-DRP-*, C2-IDMC-* | written |

## W-C Confirmation

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-C-1 | `confirmation` container after success | U-BK-4 | written |
| W-C-2 | `confirmation-reference` text EXACTLY the reference | U-BK-5 (fullmatch + API match) | written |
| W-C-3 | `confirmation-details` contains restaurant name + table label + local start | U-BK-6 | written |

## W-L Lookup (`/lookup`)

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-L-1 | lookup-reference-input / lookup-submit | U-TID, U-LKP-* | written |
| W-L-2 | reservation-detail when found | U-LKP-2 | written |
| W-L-3 | reservation-status exactly `confirmed`/`cancelled` | U-LKP-3/5 | written |
| W-L-4 | reservation-cancel-button cancels; absent once cancelled | U-LKP-5/6 | written |
| W-L-5 | reservation-error on not-found OR refused cancel | U-LKP-1/7 | written |

## W-X Upgrade (stage-1 export → stage-2)

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-X-1 | stage-2 accepts same-team stage-1 export | UPG-1 | written |
| W-X-2 | signed-in browser stays signed in | UPG-2 (API), U-UPG-2 (UI) | written |
| W-X-3 | retained reference works via lookup path | UPG-3 | written |
| W-X-4 | lost-response booking retryable post-import, same key+body → original confirmation | UPG-4, U-UPG-3 | written |
| W-X-5 | scope: import between requests; no in-flight migration; no reload needed | U-UPG flow | written |
| W-X-6 | imported table_id normalised → table_ids view rules | UPG-5/6 | written |

## W-M Combined model

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-M-1 | `combinable` = unordered PAIRS of that restaurant's table ids; never 3+ | C2-FX-1/2 | written |
| W-M-2 | unlisted pair never combinable | C2-BKC-7 | written |
| W-M-3 | not transitive: [t1,t2]+[t2,t3] ≠ {t1,t3} | C2-BKC-7 (fixture designed so) | written |
| W-M-4 | capacity = sum | C2-AVO-2 (capacity fields), C2-BKC-9 | written |
| W-M-5 | combo occupies both tables full duration | C2-AVO-7/9, C2-BKC-8, model M-OCC | written |
| W-M-6 | seeded reservations confirmed unless status:cancelled; may hold table_id or table_ids | C2-FX-4/5 | written |
| W-M-7 | single-table request formats still supported | inherited C-BK-*, C-PAT-* | written |
| W-M-8 | invalid combinable fixture entries rejected, state unchanged | C2-FX-2 (extends fixture floor) | written |

## W-O `GET /availability` options

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-O-1 | slots gain `available_options`; `available_table_ids` unchanged (singles only) | C2-AVO-1/4 | written |
| W-O-2 | options = every single + every declared pair, capacity ≥ party, no member overlap | C2-AVO-2/7/9 | written |
| W-O-3 | ordering: singles fixture order, then pairs combinable order | C2-AVO-2 exact-list | written |
| W-O-4 | pair `table_ids` in combinable order | C2-AVO-2, C2-BKC-2b | written |
| W-O-5 | `{table_ids, capacity}` entry shape | C2-AVO-5 | written |
| W-O-6 | key present on every slot | C2-AVO-3 | written |

## W-P `POST /reservations` table_ids

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-P-1 | `table_ids` accepted; `table_id` = set of one | C2-BKC-1/3 | written |
| W-P-2 | both fields → 422 validation_failed | C2-BKC-4 | written |
| W-P-3 | responses always carry table_ids; table_id iff singleton | C2-BKC-1b/3b/13/13b | written |
| W-P-4 | undeclared pair → 422 combination_not_allowed | C2-BKC-7 | written || W-P-5 | >2 tables → 422 combination_not_allowed | C2-BKC-6 | written |
| W-P-6 | member overlap → 409 table_unavailable | C2-BKC-8:* | written |
| W-P-7 | party > summed capacity → 422 party_exceeds_capacity | C2-BKC-9 | written |
| W-P-8 | duplicate id → 422 validation_failed | C2-BKC-5:dup | written |
| W-P-9 | empty set → 422 validation_failed | C2-BKC-5:empty | written |
| W-P-10 | canonical order stored/emitted | C2-BKC-2b, M-ORD | written |
| W-P-11 | unknown/foreign member → 404 | C2-BKC-10 | written |
| W-P-12 | all stage-1 errors/precedence unchanged | inherited suite zero-regression | done (0 regressions @b424a8b) |

## W-Q PATCH / moves / cancel with sets

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-Q-1 | PATCH accepts table_ids, same rules; both fields → 422 | C2-PATC-1..4 | written |
| W-Q-2 | cancel frees every member | C2-AVO-10, C2-FX-5 | written |
| W-Q-3 | moves items accept table_ids | C2-MVC-1 | written |
| W-Q-4 | no table in overlapping resulting bookings; atomic | C2-MVC-4/4b | written |
| W-Q-5 | recovery/original-receipt rules apply to combos | C2-IDMC-3/4 | written |

## W-W UI combos

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-W-1 | `slot-{a}+{b}-{HH:MM}` cells when pair available; ids combinable order; data-available | U-GRID-2, U-CMB-1/2 | written |
| W-W-2 | `confirmation-tables` contains every table label | U-CMB-5 | written |
| W-W-3 | `reservation-tables` on lookup — same | U-LKP-4 | written |
| W-W-4 | booking-summary names every table | U-CMB-3 | written |
| W-W-5 | single-table cell/confirmation/lookup unchanged | U-BK-* regression | written |

## W-N Concurrency

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-N-1 | linearizable; same results as some serial order | C2-CONC-1..3 | written |
| W-N-2 | requirements hold at every read; occupancy conservation per table incl. combo members | C2-CONC-4, model replay | written |
| W-N-3 | 50-way idempotent create: one 201, rest 200 identical | C2-IDMC-7 | written |

## W-H Inherited & deployment

| Req | Clause | Checks | Status |
|---|---|---|---|
| W-H-1 | every stage-1 clause still applies | full inherited suite via checks.py | done (225 inherited PASS + official stage-1 120/120 in s2 image) |
| W-H-2 | hardened demo mode disables `/_test/*`; default keeps them | C2-HRD:* | written |
| W-H-3 | stage-2 independently buildable, no runtime outbound net | official harness + isolated mode | done (isolated run completed @b424a8b) |

## Flags / gaps (explicit; coordinator rulings treated as falsifiable claims)

- F-1 Precedence among combination errors vs grid/hours/capacity when several
  apply simultaneously is unstated; model picks shape -> existence -> grid ->
  hours -> combination -> capacity -> occupancy. (obs)
- F-2 `table_ids` wrong element types / null field: spec's type rule is
  field-level; asserted loosely (400|422), never 5xx. (obs)
- F-3 Seed carrying BOTH `table_id`+`table_ids`: asserted 422 by "either";
  inference, not literal text. (obs)
- F-4 Declared-but-unavailable pair cells: asserted absent (count-exact
  U-GRID-4) per "shown when available"; if hidden checks demand
  rendered-false cells, revisit (coord R2-5 fallback noted). (flag)
- F-5 Lost cancel response: spec scopes booking-uncertain to booking submit;
  cancel loss unspecified — not asserted. (gap, matches R2-9)
- F-6 "Browser must not manufacture success from cache" — proven indirectly
  via U-DRP (retry goes to server); full offline-cache audit is design
  review. (obs)
- F-7 Visual-quality clauses (hierarchy, contrast, focus) screenshot-captured
  for review; not automatable pass/fail. (obs)
- F-8 UI fixture uses all-week r_ui + dedicated closed-day r_closed; grid
  cross-check is API-authoritative per slot.
- F-9 (self-finding, disclosed honestly): my U-* waits queried each testid
  separately and MISSED the OR-selector hazard the shipped suite exposed —
  `wait_for_selector("availability-grid, no-slots")` locks onto the first DOM
  match. Found via official harness stage-2 run (13 timeouts), not by my
  derived suite. Regression guard U-GRID-6a/b added post-hoc.
- F-10 model.py NOW0 is snapped to the slot grid (was vacuous when
  run-minute % slot_minutes != 0 — every generated start would be off-grid,
  exercising nothing). Same latent flaw exists in verification/stage-1/
  model.py; its clean runs may have depended on start-minute luck.
- F-11 (self-finding): model.py _validate_target originally omitted the
  capacity check on move targets. Seed-13 replay at b424a8b disagreed
  (model want 409/table_unavailable, service 422/party_exceeds_capacity);
  direct service probe confirmed the service response is spec-correct
  (party 8 onto singleton cap-4). Fixed in model; seeds 7/13/42 re-run.
