# Requirements matrix — Tablekeeper stage 4

Source: official spec `tablekeeper/spec/stage-4.md` @ commit
`803560d2a678ace1414465c098eb0ab5380ffade` (D:\tk-official).
**All stage-1, stage-2 and stage-3 rows continue to apply unchanged.** Every
row below is a testable stage-4 clause. Rows marked RULING resolve a sentence
that could be read two ways; rulings choose the reading that keeps every stated
invariant true.

## RP — Closure replan preview

| # | Clause | Check idea |
|---|---|---|
| RP-1 | `POST /restaurants/{id}/replans` requires manager auth and an idempotency key. No token → 401; authenticated non-manager → 403; unknown restaurant → 404 | auth matrix |
| RP-2 | Body is a JSON object containing `table_id`, `from`, and `to`; unknown fields are ignored | body/unknown-field probes |
| RP-3 | `table_id` must name an existing table in that restaurant; unknown/cross-restaurant table → 404 | unknown-table probe |
| RP-4 | `from` and `to` are instants with explicit offsets and `from < to`; malformed, naive, wrong-type, equal or reversed values → 422 `validation_failed` | timestamp sweep |
| RP-5 | The proposed closure is the absolute half-open interval `[from,to)`; touching endpoints do not overlap | boundary probes |
| RP-6 | The considered set is every confirmed booking at this restaurant overlapping the closure interval; cancelled, non-overlapping and other-restaurant bookings are not considered | set membership probe |
| RP-7 | Planning must support up to 6 tables, 4 declared pairs and 6 considered bookings; inputs above those limits may fail, and this implementation returns 422 `planning_limit` | R4-7 limit probe |
| RP-8 | Every considered booking keeps reference, owner, party size, start, end and accepted terms; its assigned option must have enough capacity under **that booking's** accepted terms | invariant diff |
| RP-9 | Assignments may be a singleton or a declared pair only; undeclared sets are impossible | candidate-space probe |
| RP-10 | A resulting assignment must not conflict with fixed bookings, other assignments, already-applied closures, or the proposed closure | conflict matrix |
| RP-11 | Diners' cancellation cutoffs do not block an operator repair | inside-cutoff fixture probe |
| RP-12 | No booking may disappear or be cancelled; every considered booking appears exactly once | response/set invariant |
| RP-13 | Feasible plans minimize lexicographically: moved count, total unused seats, then option-rank vector in ascending reservation-reference order | controlled alternatives |
| RP-14 | Option ranks are singles in fixture order first, then declared pairs in declaration order, starting at 0 | rank-vector probe |
| RP-15 | Preview returns 201 with `plan_id`, current `restaurant_revision`, `closure`, `assignments`, `moved_count`, `unused_seats` | exact shape |
| RP-16 | `assignments` contains every considered booking in reservation-reference order; each entry has `reference`, canonical `table_ids`, `changed` | ordering/shape |
| RP-17 | `moved_count` counts bookings whose canonical table set changes; `unused_seats` is total assigned capacity minus party size across all considered bookings | arithmetic probe |
| RP-18 | Preview stores only a plan: no closure, occupancy, reservation revision/history, series revision, restaurant revision or idempotent side effect beyond the stored successful response | pre/post state diff |
| RP-19 | No feasible plan returns 409 `no_feasible_plan` and changes nothing | capacity exhaustion probe |
| RP-20 | Preview is idempotent: first success 201; same key/path/body replays original response with 200; same key/different body → 409; failures do not claim the key | replay/reuse/failure retry |

## RA — Plan apply and applied closures

| # | Clause | Check idea |
|---|---|---|
| RA-1 | `POST /restaurants/{id}/replans/{plan_id}/apply` requires manager auth and an idempotency key; body `{}`; unknown fields ignored | auth/body probes |
| RA-2 | Unknown plan or a plan from another restaurant returns 404 | wrong-path plan probe |
| RA-3 | Any intervening restaurant revision invalidates a pending plan: 409 `stale_plan`, changing nothing | write between preview/apply |
| RA-4 | A plan already applied under a different key returns 409 `plan_already_applied`; replaying the successful key returns the original response with 200 even after later changes | apply replay matrix |
| RA-5 | Application is atomic and linearizable: concurrent applications cannot leave partially moved bookings | race probe |
| RA-6 | Application records the closure and all assignments together | state/export probe |
| RA-7 | Each moved booking increments reservation revision once and gains one `reassigned` history entry; accepted terms, owner, times and identity remain identical | history/decision diff |
| RA-8 | A reassigned history entry uses a `table_ids` change and carries `plan_id`; unmoved bookings gain no history/revision | exact history shape |
| RA-9 | Restaurant revision increments once for the whole successful plan application; preview, failure, replay and unrelated restaurant writes do not increment it | export/internal counter |
| RA-10 | Apply returns 201 `{plan_id, restaurant_revision, reservations:[...]}`; reservations include every considered booking in reference order | response shape/order |
| RA-11 | Applied closures exclude singles and pairs containing the closed table from availability for overlapping intervals | availability probe |
| RA-12 | Applied closures reject conflicting creates, amendments, moves and generated series occurrences with 409 `table_unavailable` | write matrix |
| RA-13 | With `explain=true`, `no_overlap` is false for a closure exactly as for a conflicting booking | explanation probe |
| RA-14 | A closure at another restaurant does not invalidate a plan or block availability here | cross-restaurant probe |
| RA-15 | The closure remains active for later planning; a second preview must account for previously applied closures | sequential plans |

## SA — Series amendments

| # | Clause | Check idea |
|---|---|---|
| SA-1 | `POST /series/{series_id}/amend` is an owner-only idempotent write; no token → 401; unknown or foreign series → 404 | auth matrix |
| SA-2 | Body requires `expected_revision`, `from_index`, `local_time`; unknown fields ignored | missing/unknown fields |
| SA-3 | `expected_revision` is a positive integer; `from_index` is an integer in `0..count-1`; booleans and non-integers are invalid | type/range sweep |
| SA-4 | `local_time` is exactly `HH:MM` in `00:00..23:59`; malformed/out-of-range values → 422 | format sweep |
| SA-5 | Mismatched `expected_revision` returns 409 `stale_revision` before any occurrence cutoff or booking validation | stale + invalid future field probe |
| SA-6 | Eligible occurrences are indices at/after `from_index`, excluding cancelled occurrences and occurrences marked `exception` | eligibility probe |
| SA-7 | Each eligible occurrence changes clock time on its original scheduled local date, retaining reference, owner, party size and current table selection | occurrence diff |
| SA-8 | An occurrence with identical resulting fields is a no-op and retains terms, revision and history | same-time amend |
| SA-9 | Each real change checks the old accepted cutoff first, then adopts the policy for its resulting start date, like individual PATCH | cutoff/policy probe |
| SA-10 | Resulting occurrences must not conflict with unchanged occurrences, other bookings, or applied closures | conflict matrix |
| SA-11 | Failure is atomic: no histories, reservation/series/restaurant revisions, exception flags, occupancy or idempotency claim survive | post-fail export/retry |
| SA-12 | Non-occupancy errors take precedence in occurrence-index order; if none fail, an occupancy conflict returns 409 `table_unavailable` | ordered-error probe |
| SA-13 | Success returns 201 with the current full series response in index order | shape check |
| SA-14 | Each changed occurrence gains one ordinary `changed` history entry and one reservation revision | per-occurrence history |
| SA-15 | Series revision and restaurant revision each increase once for the whole operation if anything changed | counter check |
| SA-16 | Series amendments do not mark occurrences `exception` | exception flag check |
| SA-17 | All-no-op or empty eligible sets succeed without changing revisions/history | no-op/exception-only probes |
| SA-18 | Replay returns the original response with 200 even after later edits or cancellations | replay after mutation |
| SA-19 | Two concurrent amendments from the same expected series revision cannot both make a real change | race probe |
| SA-20 | Series occurrences moved by a seating repair preserve exception flags, scheduled dates, identities and accepted terms; each affected series revision increases once per plan application if at least one member moved | repair + series probe |

## X — Upgrade and import continuity

| # | Clause | Check idea |
|---|---|---|
| X-1 | Stage-4 accepts exports produced by the same team's stage-1, stage-2 and stage-3 services | three upgrade legs |
| X-2 | Imported series remain usable, including moved and cancelled occurrences; imported reservations retain references/histories/revisions/terms | import → series amend |
| X-3 | Earlier booking and series receipts, sessions, links and idempotent retries remain valid after import | replay/token/lookup probes |
| X-4 | Stage-4 export/import round-trips applied closures, pending/applied plans, reservations, series, policies, revisions, histories and idempotency records without losing behavior | export → import → apply/replay |
| X-5 | Failed imports remain atomic and leave every prior behavior unchanged | malformed/invalid import |

## D — Dispatch-derived delivery clauses

| # | Clause | Check idea |
|---|---|---|
| D-1 | `stage-4/` is a complete independently buildable service: Dockerfile, RUN.md, source, tests, inherited UI, no symlinks/submodules/nested `.git` | clean-clone build |
| D-2 | Stage-4 begins as a verbatim copy of frozen stage-3 (`d9d04ba` product tree) before feature commits | first scaffold commit diff |
| D-3 | Hardened deployment mode still disables `/_test`; judge image keeps it enabled by default | `TK_HARDENED` probe |
| D-4 | Runtime zero outbound network including UI assets; no runtime dependency fetch | isolated run + asset audit |
| D-5 | Stage-4 requires no new screens; existing availability, confirmation and lookup screens must reflect an applied closure/plan through the API | inherited UI + closure smoke |
| D-6 | Message budget discipline: one phase-ready notice and one verdict/handoff per seat; no status chatter | room process |

## Rulings (stage 4)

- **R4-1** Replan preview/apply use the same request pipeline as the stage-3
  policy write: parse JSON object → authenticate → require idempotency key →
  resolve replay → endpoint checks under the writer lock. Test independent
  error cases separately; when auth and resource errors coincide, auth/key
  checks win.
- **R4-2** `manager` means membership in the restaurant's
  `manager_user_ids`. Managers gain no extra access to diners' private
  reservation reads beyond this operator endpoint.
- **R4-3** Replan `from`/`to` are absolute instants, not restaurant-local
  fields. Parse RFC 3339 timestamps with explicit offsets and compare epochs;
  response `closure.from`/`closure.to` echo the accepted request strings while
  behavior uses their instants.
- **R4-4** Considered-set overlap uses absolute half-open intervals:
  `[start_epoch,end_epoch)` vs `[from,to)`. A booking ending exactly at `from`
  or starting exactly at `to` is not considered.
- **R4-5** A proposed closure blocks any candidate containing `table_id` for
  assignments whose booking interval overlaps `[from,to)`. A singleton closure
  also blocks every declared pair containing that singleton.
- **R4-6** Fixed bookings are all confirmed bookings outside the considered
  set. They retain assignments but still block candidate occupancy.
- **R4-7** The planning limits are enforced deterministically: >6 tables, >4
  declared pairs, or >6 considered bookings returns 422 `planning_limit`
  before search. Inputs at the limits must be supported.
- **R4-8** Candidate options are every singleton in fixture order followed by
  every declared pair in declaration order. Capacity comes from the booking's
  own accepted terms, not the currently selected policy.
- **R4-9** `unused_seats` is the sum over all considered bookings of assigned
  capacity minus party size, including unchanged assignments.
- **R4-10** The third optimization key is the vector of assigned option ranks
  ordered by ascending reservation reference. There is no secondary stable
  choice beyond that spec-defined vector; implementation search may be
  deterministic internally.
- **R4-11** `restaurant_revision` in a preview response is the current stored
  revision and does not increment it. `restaurant_revision` in an apply
  response is the post-apply incremented revision.
- **R4-12** A pending plan is bound to the restaurant id and the restaurant
  revision at preview. Any successful revision-producing write to that
  restaurant — create, real amendment, cancellation, policy publication,
  series adoption/amendment, move batch, or plan application — makes it stale.
- **R4-13** Replay of a successful preview remains the original response even
  if the plan later becomes stale or is applied; idempotent replay is resolved
  before endpoint-specific state checks.
- **R4-14** For apply, an already-applied plan under a different key returns
  `plan_already_applied` even though the restaurant revision has advanced;
  `stale_plan` is for a pending plan invalidated before application.
- **R4-15** Applied closures are part of occupancy for availability and all
  later bookings/amendments/moves/series writes. Closure conflicts return
  `table_unavailable` after non-occupancy validation has passed.
- **R4-16** A `reassigned` history entry has event `reassigned`, a
  `table_ids` change with complete before/after lists (even single→single),
  top-level `plan_id`, resulting revision and accepted terms. It does not
  change `starts_at_local`, `starts_at`, `ends_at`, party size or terms.
- **R4-17** Replan repair ignores diner cancellation cutoffs but does not
  bypass ownership/resource visibility for the manager endpoint.
- **R4-18** Series amend requires all three body fields shown by the spec:
  `expected_revision`, `from_index`, `local_time`. Missing fields are 422.
- **R4-19** `expected_revision` on series amend names the series revision,
  not a reservation or restaurant revision. It is checked once before any
  occurrence-level validation.
- **R4-20** Series amendment preserves each occurrence's current canonical
  `table_ids`; it changes clock time only. Capacity and duration are
  rechecked under the policy applicable to the resulting local start date.
- **R4-21** Series amendment occupancy considers the entire resulting set at
  once: unchanged occurrences, non-series bookings and applied closures all
  block. Nothing mutates until all eligible occurrences validate.
- **R4-22** A seating repair is not a diner amendment: it does not mark a
  series occurrence `exception`, does not alter accepted terms, and preserves
  existing exception flags. It bumps each affected series revision once per
  application.
- **R4-23** Stage-4 export/import preserves the internal `plans` and
  `closures` state needed to keep pending plan apply, applied-closure
  occupancy and replays working. Older exports lacking those fields import as
  empty sets.
- **R4-24** Stage-4 adds no required browser screens or testids. UI changes
  are not expected; any forced compatibility change must remain within the
  inherited stage-2 surface and be flagged to coordinator.
