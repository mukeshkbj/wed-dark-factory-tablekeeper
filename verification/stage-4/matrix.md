# Stage-4 verification matrix — clause → check coverage

Derived from `D:\tk-official\tablekeeper\spec\stage-4.md` plus coordinator
rulings R4-1..R4-24 (`docs/requirements-matrix-stage-4.md`). The matrix is a
claim list to falsify; checks are spec-derived black-box probes.

Inherited behaviour (stage-1/2/3) is re-run verbatim via dynamic module
loading — `checks.py` loads `stage-3.checks`, which loads `stage-2.checks`,
which loads `stage-1.checks`. No inherited check is weakened.

## Replan preview (RP) — `POST /restaurants/{id}/replans`

| Clause / ruling | Coverage |
|---|---|
| Pipeline: parse → auth → idem-key → replay → endpoint checks under writer lock (R4-1) | C4-RP-1a..g, C4-RP-20a..d |
| Manager-only = `manager_user_ids` member (R4-2) | C4-RP-1b/1c (non-manager 403, bogus 401) |
| from/to are RFC-3339 instants with explicit offset; response echoes strings (R4-3) | C4-RP-4:* (naive/int/str/null/bool/equal/reversed/missing all 422; `Z` accepted), C4-RP-15b echo |
| Half-open `[from,to)` overlap (R4-4) | C4-RP-5:to/from (boundary bookings excluded) |
| Considered = confirmed bookings at restaurant overlapping interval | C4-RP-6:set/n (exactly 3), C4-RP-5:cancelled, C4-RP-6:setup-xr (cross-restaurant excluded) |
| Candidate order: singletons in fixture order, then declared pairs (R4-8) | C4-RP-17 (t_a over t_c on unused), C4-RP-20a..c (pair chosen when no singleton fits, pair touching closed table skipped) |
| Capacity via each booking's accepted terms, not current policy | implicit in party/cap fixtures; terms checked at apply (C4-RA-7b) |
| Fixed bookings / other proposed assignments / applied+proposed closures block candidates (R4-5, R4-6) | C4-RP-13d/e (t_b held → t_c), C4-RA-15a..d/x (applied closure blocks later plans incl. pairs) |
| Manager repair bypasses diner cutoffs (R4-17) | covered by preview creating plans regardless of booking cutoffs (all previews inside 120min fixtures) |
| Planning limits: >6 tables / >4 pairs / >6 considered → 422 `planning_limit` (R4-7) | C4-RP-7a/b (7 considered → 422), C4-RP-7c (6 ok) |
| Optimization: min moved → min unused → rank vector by ascending reference (R4-9/10) | C4-RP-13c..e, C4-RP-17, C4-RP-9, C4-RP-9b, C4-RP-21b/c |
| Response shape `{plan_id, restaurant_revision, closure, assignments[], moved_count, unused_seats}`, assignments in reference order (R4-11) | C4-RP-15/15b/16, C4-RP-6:order |
| Preview stores pending plan only — no occupancy/history/revision/closure changes (R4-11) | C4-RP-18a..d (rev unchanged, no history, availability intact) |
| `no_feasible_plan` → 409, nothing changes | C4-RP-19a..d |

## Plan apply (RA) — `POST /restaurants/{id}/replans/{pid}/apply`

| Clause / ruling | Coverage |
|---|---|
| Manager + idem key required; `{}` body, unknown fields ignored | C4-RA-1a..d |
| Unknown plan / plan of another restaurant → 404 | C4-RA-2a/2b |
| Any intervening revision-producing write → 409 `stale_plan` (R4-12) | C4-RA-3/3b/3c, C4-RA-SM:{create,patch,cancel,move,policy,series_create} (coherence-probed) |
| No-op / failed writes don't stale | C4-RA-3d/3e (no-op PATCH → still applies) |
| Cross-restaurant writes don't stale | C4-RA-14a/14b |
| `plan_already_applied` under a different key (R4-14) | C4-RA-4c/4d, C4-CON-1b |
| Replay of successful apply key → original response 200 even after later changes (R4-13/14) | C4-RA-4a/4b |
| Response shape `{plan_id, restaurant_revision, reservations[]}` | C4-RA-10/10b/10c |
| Restaurant revision +1 once per plan; preview rev vs apply rev (R4-11) | C4-RA-9/9b |
| Moved bookings: rev+1, one `reassigned` entry with `table_ids` change, `plan_id`, terms preserved; unmoved untouched (R4-16) | C4-RA-7a/7b/7c, C4-RA-8/8b/8c/8t |
| Atomic application | C4-RA-SM:*:atomic, C4-CON-1b (double-apply race → exactly one 201) |
| Closures are occupancy: availability excludes singles+pairs; creates → 409 `table_unavailable`; explain `no_overlap=false` (R4-15) | C4-RA-11a/b/z, C4-RA-15x, C4-RA-12a, C4-RA-13 |
| Closures block series adoption of overlapping anchors | C4-RA-12h/12i (adoption into closure window → 409, anchor untouched) |
| Later previews plan around applied closures | C4-RA-15c/15d |
| Closure at another restaurant doesn't invalidate plan (R4-15/spec) | C4-RA-14a/14b/14c |
| Series occurrences moved by a plan keep ref/flags/terms; series rev +1 once (R4-22) | C4-SA-20a..g |

## Series amend (SA) — `POST /series/{sid}/amend`

| Clause / ruling | Coverage |
|---|---|
| Owner-only, auth + idem key | C4-SA-1a..e |
| Required fields: expected_revision, from_index, local_time (R4-18) | C4-SA-2:*, C4-SA-2b (unknown fields ignored) |
| Type/range validation: positive non-bool int rev; index 0..count-1; HH:MM 00:00-23:59 (R4-18) | C4-SA-3:*, C4-SA-3b, C4-SA-4:* |
| Stale series revision → 409 `stale_revision` BEFORE occurrence checks (R4-19) | C4-SA-5/5b/5c |
| Eligibility: index ≥ from_index, not cancelled, not exception (R4-20) | C4-SA-6a/6b/6c, C4-SA-17/17b |
| Clock-time-only change on original local date; refs/owner/party/table kept (R4-20) | C4-SA-7a/7b/7c |
| No-op → success without revision/history change | C4-SA-8/8b |
| Old accepted cutoff checked first, then policy for resulting date (R4-21) | C4-SA-9a/9b/9c, C4-SA-12 |
| Resulting occurrences can't conflict with unchanged ones, other bookings, closures (R4-21, R4-15) | C4-SA-10a..c, C4-SA-21a..e |
| Non-occupancy errors take precedence in index order | C4-SA-12 (grid-422 beats occupancy-409) |
| Fully atomic failure: nothing survives | C4-SA-11a/11b, C4-SA-21d/21e |
| 201 full series response, index order | C4-SA-13 |
| Changed occurrences: one `changed` entry + rev+1; series+restaurant rev +1 once | C4-SA-14, C4-SA-15 |
| Amend never sets exception flags | C4-SA-16 |
| Replay returns original response after later edits/cancels | C4-SA-18a/18b/18c |
| Same-revision race: at most one real change | C4-SA-19/19b |

## Upgrade / import (X)

| Clause / ruling | Coverage |
|---|---|
| s1/s2/s3 exports import into s4 (R4-23) | X-s1-1, X-s2-1, X-s3-1 (+ _check_imported per leg) |
| Old exports lacking plans/closures import them EMPTY | X-s3-4c (no phantom closures), X-s4-5 (keys present in s4 export) |
| Imported reservations: rev1/policy-0 normalisation, history/decision, pending-retry recovery, token/ref continuity | X-*-3a/3b/3c/4a/4b/4c |
| Imported bookings adoptable into series | X-s1-2, X-s2-2 |
| s3 exports carry policies+series through | X-s3-4a/4b |
| s4 round-trip preserves pending+applied plans, closures, series, histories | X-s4-5/6a..d/7/7b/8/8b |
| Failed import atomic | X-5:wrong_track/wrong_ver/no_state, X-5b |

## Concurrency / atomicity (CON)

| Claim | Coverage |
|---|---|
| Concurrent previews coexist | C4-CON-1a |
| Double-apply race: exactly one 201 | C4-CON-1b |
| Second pending plan stales after first applies | C4-CON-1c |
| Apply vs create race: legal outcomes only (winner consistent) | C4-CON-2a/2b |
| Out-of-window create still stales (any revision write) | C4-CON-3a/3b |
| Concurrent series amends, same base revision: ≤1 real change | C4-SA-19/19b |

## Hardened mode (D-3)

| Claim | Coverage |
|---|---|
| `/_test/*` -> 404 under TK_HARDENED=1 | C4-HRD:/_test/reset,export,import |
| `/health` + UI still served | C4-HRD-health, C4-HRD-ui |

## Inherited / UI (D-5, R4-24)

| Claim | Coverage |
|---|---|
| No new browser surfaces needed | `ui_checks.py` delegates verbatim to stage-2 UI suite (82 checks incl. OR-selector probes U-GRID-6a/6b) |
| All stage-1/2/3 API checks re-run on stage-4 | `--inherited-only` and default full run compose s1.SECTIONS + s2.SECTIONS2 + s3.SECTIONS3 + SECTIONS4 |
