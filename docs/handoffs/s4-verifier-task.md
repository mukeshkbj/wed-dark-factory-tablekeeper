@mukeshkbj/tk-verifier — STAGE 4 VERIFICATION DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-verifier.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-4.md`, inherited specs `stage-1.md`/`stage-2.md`/`stage-3.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-4.md`. Treat the matrix as a claim list to falsify, not gospel.

CONTEXT: stages 1–3 are FROZEN. Stage-3 accepted product tree is `d9d04ba`; verifier evidence through `e5679e3`; coordinator freeze commit `7e957fe`. Work only in `D:\WED Dark factory\verification\stage-4\` and committed evidence paths. Never repair product code.

TASK, two phases:

PHASE 1 (start now, parallel to implementation): build `verification/stage-4/` — your own clause-by-clause matrix from the SPEC TEXT plus a spec-derived check suite. Cover at minimum:

- Replan preview: manager auth/idempotency; explicit-offset interval parsing; half-open overlap; considered set; singleton/declared-pair candidates; per-booking accepted-terms capacity; fixed bookings/other assignments/prior closures/proposed closure; deterministic planning limits; optimization order including rank vector; exact response shape/order; preview causes no occupancy/history/revision changes; `no_feasible_plan` atomicity.
- Apply/stale/replay: wrong restaurant/unknown plan; `stale_plan` on any intervening revision-producing write; cross-restaurant non-invalidation; `plan_already_applied`; original-response replay after later changes; atomic concurrent application; once-per-plan restaurant revision.
- Applied closures: availability and `explain.no_overlap`; creates/PATCH/moves/series adoption+amend conflicts; boundary behavior; later previews account for closures; `reassigned` history shape with `table_ids` + `plan_id`; moved series occurrence flags and series revision.
- Series amend: auth/ownership/idempotency; required field/type/range validation; stale series revision precedence; index eligibility excluding cancelled/exception; original-date clock-time change; no-op/empty set behavior; per-occurrence cutoff then resulting-date policy; batch occupancy including closures; error precedence; atomicity; once-per-operation counters; replay after later edits/cancels; same-revision race.
- Upgrade: stage-1/2/3 exports into stage-4; imported series including moved/cancelled occurrences; pending/applied plans and closures if present; sessions/receipts/histories/idempotent retries; stage-4 round-trip and atomic failed import.
- Inherited: rerun stage-1/2/3 suites or targeted regression so stage-4 does not regress them; inherited UI contract remains green because no new screens are required.
- Concurrency/atomicity: concurrent preview/apply, stale-plan race, apply vs booking write, series amend same revision, closure vs occupancy, import atomicity.

PHASE 2 (on implementer handoffs): re-run everything at the named revision, then official harness from `D:\tk-official`:
`D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 4 --out <NEW dir>` and the same with `--mode isolated` (fresh out dirs; suggest `D:\WED Dark factory\evidence\harness\s4-runN`). Report verdict CONFIRMED or a numbered findings list citing exact clauses/revisions.

RULES: check real commits/diffs and test bodies, not summaries. Findings route through coordinator; do not patch product code. Message budget is real — one phase-1 ready notice and one verdict message; no status chatter.

DONE = verdict message to the room addressed to @mukeshkbj/tk-coordinator naming exact checked SHA, every command + counts + durations, held-open items. Then end your turn.
