# tk-verifier stage-3 requirements matrix

Derived from `tablekeeper/spec/stage-3.md` @803560d (coordinator matrix
treated as a claim list to falsify; rulings cited where they pick a reading).
All stage-1/stage-2 rows continue to apply via the inherited suites
(`checks.py` default run executes s1+s2+s3; `--inherited-only` isolates them).

Legend: → = check id(s) in `checks.py`; X: in `upgrade_checks.py`;
U: in stage-2 `ui_checks.py` via the `ui_checks.py` shim.

## E — Availability explanations

| Row | Clause (spec-derived) | Check |
|---|---|---|
| E-1 | `explain` optional; only literal `true` accepted; `false`/`1`/empty/other case/repeated → 422 `validation_failed` | C3-E-1:* (8 variants incl. repeat/mixed) |
| E-2 | Without `explain` the response keeps the stage-1/2 shape — no explanation fields | C3-E-2/b |
| E-3 | With `explain=true`, every slot carries `explain` | C3-E-3/4 |
| E-4 | Every restaurant table appears exactly once, fixture order, available or not | C3-E-4 |
| E-5 | Entry fields: `table_id`, `policy_version`, `available`, `rules` | C3-E-5 |
| E-6 | `rules` = capacity then no_overlap for every table; both may be false; none omitted | C3-E-6, C3-E-T1/T3/T4 |
| E-7 | `available` true iff both rules hold | C3-E-7/8 (per-slot/per-table truth) |
| E-8 | available-true ids == `available_table_ids`, same order | C3-E-7/8 |
| E-9 | Closed day → `slots:[]`; fully-unavailable slot still listed with full explain | C3-E-9, C3-E-9b |
| E-10 | Policies can change slot values/grid/hours and hence explanations | C3-E-10 |
| E-11 | `policy_version` = policy selected for that slot's local date (0 = fixture) | C3-E-11, C3-E-11b |
| R3-1 | `available_options` still present under `explain`; per-table only | C3-E-R1 |

## P — Booking policies

| Row | Clause | Check |
|---|---|---|
| P-1 | `manager_user_ids` fixture optional; absent → `[]` | C3-P-1 |
| P-2/R3-2 | Fixture validation: non-list, non-string/over-length/unknown user ids → 422 + state unchanged; dupes collapse | C3-P-2:*, 2c/2d/2e |
| P-3 | Auth matrix: no/bad token → 401; authed non-manager → 403 `forbidden`; unknown restaurant → 404; 401 beats 404 | C3-P-3a..f |
| P-4 | Manager role grants no access to other diners' private views | C3-P-4a/4b |
| P-5/P-4 | Publish needs idempotency key; stage-1 replay rules | C3-P-5a/5b |
| P-6/R3-3 | Replay → 200 original body, no new version; reuse → 409; failed write frees key; version alloc on success only | C3-P-6a..c, C3-P-7, C3-P-8a..c |
| R3-9 | Key namespace is per method+path+body across new write paths | C3-P-9 |
| P-7 | Complete policy required; every missing field → 422 | C3-P-10:* |
| P-8 | Unknown fields ignored, not echoed | C3-P-11/11b |
| P-9 | `effective_from` real YYYY-MM-DD (bad month/day/format/int/null/bool → 422); past dates legal | C3-P-12:* |
| P-10 | `slot_minutes`/`reservation_duration_minutes` int 1..1440; `cancellation_cutoff_minutes` int 0..10080; bool/float/str/null → 422 | C3-P-13:* |
| P-11 | `opening_hours` stage-1 rules, no duplicate weekdays; partial week = complete replacement (absent = closed, R3-14) | C3-P-14:* |
| P-12 | `capacities` names exactly the restaurant's tables, int 1..100 | C3-P-15:* |
| P-13 | Invalid publish → 422, no version, no state change; versions contiguous per restaurant from 1 | C3-P-16/16b |
| P-14 | Policies immutable — no update/delete path | C3-P-17:* |
| P-15 | `GET` policies public, `{"policies":[...]}`, publication order, policy 0 omitted | C3-P-19a..c |
| P-16 | Selection: greatest `effective_from` ≤ booking local start; ties → greatest `policy_version` | C3-P-20a..c, C3-P-21a/b |
| P-17 | Restaurant detail keeps fixture config; decisions use selected policy | C3-P-22, C3-E-10 |
| P-18 | Publication never retroactively edits accepted bookings | C3-T-4 |

## T — Accepted terms, revisions, amendments

| Row | Clause | Check |
|---|---|---|
| T-1 | Reservation responses gain `revision` + `accepted_terms` on create/get/list | C3-T-1/1b/1c |
| T-2 | `revision` 1 at creation | C3-T-2 |
| T-3/R3-13 | `accepted_terms` = whole selected policy minus `effective_from`, incl. full capacity map | C3-T-3/3b |
| T-4 | Policy publication leaves existing bookings/terms/end times untouched (R3-18: smaller capacity keeps booking valid) | C3-T-4 |
| T-5 | Old idempotent responses keep original revision/terms | C3-P-6b; s1 C-IDM-7b on create replay |
| T-6 | Cancel uses accepted cutoff vs current start | C3-T-6 (post-policy cancel under old terms) |
| T-7 | Cancel bumps revision once; repeat cancel does not (inherited 200 no-op) | C3-T-7/7b/7bb/7c |
| T-8 | Real amendment: old accepted cutoff first, then all resulting fields vs resulting-date policy; atomic term+end replacement, +1 revision | C3-T-9/9b |
| T-9 | No-op amendment retains terms/end/revision/history, still needs editable booking | C3-T-10/10b/10c |
| T-10 | Failed amendment changes nothing | C3-T-11/11b |
| T-11/R3-4 | `expected_revision` optional positive int; mismatch → 409 `stale_revision` before cutoff/validation; 0/neg/float/str/bool/null → 422 | C3-T-12a..c, C3-T-13:* |
| T-12 | Concurrent amends on one revision: at most one real change | C3-T-14 |
| T-13 | Unknown PATCH fields ignored | C3-T-15/15b |

## H — History and decision

| Row | Clause | Check |
|---|---|---|
| H-1 | `GET /reservations/{ref}/history` own record, oldest first | C3-H-1/1b |
| H-2/R3-10 | Owner-only; foreign/anonymous/bad token/unknown ref → same 404 `not_found` | C3-H-2a..d, C3-H-12/12b |
| H-3 | Cancelled reservations retain readable history | C3-H-3, C3-H-8b..d |
| H-4 | `seq` 1..n step 1; `seq` order = `at` order | C3-H-4 |
| H-5 | `created` names table_id|table_ids, starts_at_local, party_size, all `from:null` | C3-H-5, C3-B-2 |
| H-6 | `changed` names only actual changes, ordered table_id, starts_at_local, party_size | C3-H-6b/6d |
| H-7 | No-op PATCH records no entry | C3-H-7a/7b |
| H-8 | `cancelled` has `changes:[]` and is terminal | C3-H-8b..d |
| H-9 | Idempotent create replay records nothing | C3-H-9 |
| H-10 | Every entry carries resulting `revision` + complete `accepted_terms`; old entries never gain newer terms | C3-H-10, C3-H-13c |
| H-11 | `GET .../decision` → `{reference, revision, accepted_terms}`, incl. after cancel | C3-H-11/11b |

## S — Recurring series

| Row | Clause | Check |
|---|---|---|
| S-1 | `POST /series` auth + key; body `{anchor_reference, count, interval_weeks}` | C3-S-1a/1b, C3-S-4b:* |
| S-2 | Anchor: caller-owned, confirmed, within accepted cutoff | C3-S-3a..c (+cutoff via anchor probes) |
| S-3 | Unknown/foreign anchor → 404; cancelled → 409 `reservation_cancelled`; adopted → 409 `already_in_series` | C3-S-3a/3b/3c/3d |
| S-4 | `count` int 2..12, `interval_weeks` int 1..4; bool/float/str → 422 | C3-S-4:* |
| S-5 | Occurrence 0 = anchor: identity/revision/terms/history/original response unchanged | C3-S-5/5b, C3-S-22b |
| S-6 | Occurrence i = anchor local date + i·interval·7d, same clock | C3-S-6 |
| S-7 | Each generated occurrence selects its own date's policy | C3-S-7 |
| S-8 | Nonexistent local time → whole adoption 422 `invalid_local_time`; folds use first-occurrence rule | C3-S-8a..f (2027-03-28 gap, 2026-10-25 fold) |
| S-9/R3-7 | Generated occurrences inherit party size + canonical table selection incl. pairs | C3-S-9, C3-S-40c/40d |
| S-10 | Atomic adoption: no partial series/reservations/histories/counters/key claim on failure | C3-S-10a..d |
| S-11/R3-16 | First failing occurrence in index order determines the error | C3-S-11 |
| S-12 | 201 `{series_id, revision:1, interval_weeks, occurrences[]}` all count, index order | C3-S-12/12b/12c |
| S-13 | Distinct ordinary refs; stable under later changes | C3-S-12d + patch/cancel probes |
| S-14 | Occurrences list normally, occupy tables, have own histories | C3-S-14a..c |
| S-15 | `GET /series/{id}` owner-only; foreign/anon → 404; current states | C3-S-15a..d |
| S-16 | Real PATCH → permanent `exception:true` + series revision +1 | C3-S-16a/16b |
| S-17 | No-op/failed PATCH changes neither | C3-S-17a/17b |
| S-18 | Cancel occurrence → series rev +1, retained, `exception` stays false; repeat = no-op | C3-S-18a..d |
| S-19 | Cancelling anchor does not cancel siblings | C3-S-19a/19b |
| S-20 | Ordinary cutoff + `expected_revision` apply to occurrence writes | C3-T-13 on occurrences; C3-M-2 |
| S-21 | Adoption increments restaurant revision once (internal; export-visible) | covered by X-s3 round-trip integrity |
| S-22 | Replay returns original response after later changes, no counters | C3-S-22/22b |
| S-23 | Unknown fields ignored | C3-S-12 (`zzz`) |
| S-24 | `series_id` opaque, <=64 chars | C3-S-12b |

## B — Combined-table history

| Row | Clause | Check |
|---|---|---|
| B-1 | Terms apply to combinations; pair capacity = sum of selected policy caps | C3-S-40* + C3-E-* on r_combo inherited |
| B-2/R3-6 | Pair create history uses `table_ids` from null; never `table_id` | C3-B-2/2b |
| B-3 | Pair-involving changes use `table_ids` complete lists | C3-B-3a/3b |
| B-4 | Table-set order = declared combination order | C3-B-4 |
| B-5/R3-5 | Reversed pair = same set = no-op (no entry/rev bump/exception) | C3-B-5a/5b |
| B-6 | Policy/revision/replay rules unchanged for pairs | inherited C2-* + C3-B-* |

## M — Collective moves under policies/series

| Row | Clause | Check |
|---|---|---|
| M-1 | Each real move = PATCH semantics (old cutoff then resulting-date policy) | C3-M-1a..c |
| M-2 | Per-move `expected_revision`; stale item fails batch (409) | C3-M-2 |
| M-3 | No-op move retains terms/revision/history | C3-M-3/3b |
| M-4 | Batch atomic: failure leaves every booking unchanged | C3-M-4 |
| M-5 | Each changed booking +1 revision + one `changed` entry | C3-M-5 |
| M-6 | Restaurant revision +1 once per batch (internal invariant) | export-diff observation; marked partial |
| M-7/R3-19 | Affected series +1 revision once per batch; moved occurrences become permanent exceptions | C3-M-7b/7c |
| M-8 | Failed batch/replay: no revision/history/exception changes | C3-M-2/3b + replay probes |

## X — Upgrade (upgrade_checks.py, needs s1+s2+s3 services)

| Row | Clause | Check |
|---|---|---|
| X-1 | stage-1 and stage-2 exports import into stage-3 | X-s1-1, X-s2-1 |
| X-2 | Imported reservations adoptable into series | X-s1-2, X-s2-2 |
| X-3 | Tokens, references, pending idempotent retries survive | X-*-3a..c |
| X-4/R3-20 | Imports normalise to revision 1 + policy-0 terms; history/decision served | X-*-4a..c |
| X-5 | Import atomic; bad payloads leave destination unchanged | X-5:*, X-5b |
| X-6 | stage-3 round-trip preserves policies/series/exceptions/histories/revisions/terms | X-s3-6a..e |

## D — Delivery clauses

| Row | Clause | Check |
|---|---|---|
| D-1 | stage-3 independently buildable (Dockerfile/RUN.md/src/tests/UI; no symlinks/nested .git) | repo review + harness build |
| D-2 | stage-3 began as verbatim copy of frozen stage-2 `5be5343` | `git diff 5be5343 c23f857 -- stage-3` |
| D-3 | `TK_HARDENED=1` disables `/_test/*`; default keeps them; UI still served | C3-HRD:* (--hardened) |
| D-4 | No outbound runtime deps incl. UI assets | isolated harness run + asset audit |
| D-5/R3-15 | Inherited browser surface unchanged; no new screens required | ui_checks.py shim -> 82-check s2 suite |
| D-6 | Message discipline: one phase-ready notice, one verdict | process |

## Internal invariants (R3-11)

`restaurant_revision` is internal (no endpoint). Verified indirectly via
export round-trip integrity (X-s3-6*) and per-write behavioural checks that
would diverge if revisions miscounted (C3-M-7c single-bump, C3-S-16b/18b,
C3-T-7c). Marked **partial** — no direct probe exists.

## Reference model

Stage-2 `model.py` replay covers bookings/amend/moves/cancel under policy 0.
A stage-3 model extension (policies x dated selection x series x revisions)
is planned for phase 2 if time allows; flagged as a coverage gap here rather
than implied.
