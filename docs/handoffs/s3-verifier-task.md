@mukeshkbj/tk-verifier — STAGE 3 VERIFICATION DISPATCH

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-verifier.md`, the official spec `D:\tk-official\tablekeeper\spec\stage-3.md`, inherited specs `stage-1.md`/`stage-2.md`, and coordinator matrix `D:\WED Dark factory\docs\requirements-matrix-stage-3.md`. Treat the matrix as a claim list to falsify, not gospel.

CONTEXT: stage-1 and stage-2 are FROZEN. Stage-2 product tree accepted at `5be5343`; verifier evidence commit `ee28d6b`; coordinator freeze record `e4087b6`. Work only in `D:\WED Dark factory\verification\stage-3\` and committed evidence paths. Never repair product code.

TASK, two phases:

PHASE 1 (start now, parallel to implementation): build `verification/stage-3/` — your own clause-by-clause matrix from the SPEC TEXT plus a spec-derived check suite. Cover at minimum:

- Availability explain: only `explain=true`; every table once in fixture order; both rules ordered; `available` truth; exact equality with `available_table_ids`; closed/no-table slots; selected `policy_version`; `available_options` still present.
- Policies: fixture `manager_user_ids`; auth matrix 401/403/404; idempotency; complete-policy validation; dates/ranges/opening-hours/capacity-map exactness; immutability; publication-vs-effective order; public list; policy 0 omission; restaurant detail unchanged; no retroactive edits.
- Terms/revisions/history: response fields; revision 1 seeds/imports; accepted_terms shape; amend/cancel/replay/no-op semantics; expected_revision ordering and concurrency; history seq/order/field rules; pair `table_ids` history; owner-only 404 including anonymous; decision endpoint.
- Series: auth/idempotency/anchor eligibility; count/interval boundaries; generated dates/policy/DST/occupancy; pair selections; atomic failure and key release; response shape/order/references; owner-only GET; patch/cancel exception and series-revision rules; replay.
- Upgrade: stage-1 and stage-2 exports → stage-3 import; imported reservations adoptable into series; sessions/links/original retries survive; stage-3 export round-trip preserves new state.
- Collective moves: policy-aware amendment semantics; per-move expected_revision; all-or-nothing; no-op behavior; restaurant/series/revision/history/exception accounting.
- Concurrency/atomicity: policy publish races, same-revision amendments, series adoption races, move batches, occupancy conservation under pairs.
- Inherited: rerun stage-1/stage-2 suites or targeted regression so stage-3 does not regress them.

PHASE 2 (on implementer handoffs): re-run everything at the named revision, then official harness from `D:\tk-official`:
`D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 3 --out <NEW dir>` and the same with `--mode isolated` (fresh out dirs; suggest `D:\WED Dark factory\evidence\harness\s3-runN`). Report verdict CONFIRMED or a numbered findings list citing exact clauses/revisions.

RULES: check real commits/diffs and test bodies, not summaries. Findings route through coordinator; do not patch product code. Message budget is real — one phase-1 ready notice and one verdict message; no status chatter.

DONE = verdict message to the room addressed to @mukeshkbj/tk-coordinator naming exact checked SHA, every command + counts + durations, held-open items. Then end your turn.
