@mukeshkbj/tk-verifier — STAGE 2 VERIFICATION DISPATCH [TASK — this is part 1 of 4 of your dispatch; the complete applicable spec was sent to you verbatim in this room as the three shared messages labelled "STAGE-2 SPEC PART A" (stage-2.md), "SPEC PART B" (stage-1.md lines 1–~240) and "SPEC PART C" (stage-1.md remainder). All three @mention you. Identical copies are committed at D:\WED Dark factory\docs\handoffs\s2-spec-partA.md / partB / partC, and the originals live at D:\tk-official\tablekeeper\spec\stage-1.md and stage-2.md. You need all four parts before checking.]

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-verifier.md` — it governs this whole run. Record the model id your session actually reports in your first committed artifact; the mandate header requested `swe` — report honestly.

CONTEXT: stage-1/ is FROZEN @ aae0226 — verifier verdicts there stand (phase-3 CONFIRMED @28b16f4, official 120/120 isolated). This is attempt-2 in room 9bf93138-25b0-431d-aa62-4a3dbca30155 (old room dead). All stage-1 requirements continue to apply. Coordinator matrix + rulings R2-1..R2-15: `D:\WED Dark factory\docs\requirements-matrix-stage-2.md` — treat it as a claim list to falsify, not gospel.

TASK, two phases:

PHASE 1 (start now, parallel to implementation): build `D:\WED Dark factory\verification\stage-2\` — your own clause-by-clause matrix from the SPEC TEXT (not from shipped samples) plus a spec-derived check suite. Cover at minimum:
- API: `combinable` fixture validation edges; `available_options` completeness/ordering/capacity-sum/member-occupancy; `table_ids` create/patch/moves incl. every error in the spec table (`combination_not_allowed` for undeclared pair AND >2; `table_unavailable` per member; `party_exceeds_capacity` on the sum; `validation_failed` on duplicates / both-fields / empty); response shape (`table_ids` always, `table_id` iff singleton); non-transitivity; single-format backwards compat.
- Upgrade: stage-1 export → stage-2 import; tokens survive; retained reference resolvable; a pending idempotent retry still replays the original body post-import.
- Concurrency: same-slot pair vs member races, 50-way idempotent create, no 5xx, seat-occupancy conservation asserted after every race (per table, combos included).
- UI (Playwright chromium is installed): every `data-testid` in the spec tables; out-of-order search responses; thief-between-open-and-submit → `booking-error` + preserved form; dropped/timeout booking response → `booking-uncertain` + same-key retry → original reference; double-submit replay = one reservation; lookup cancel flow; signed-out click; 375px viewport sweep; combo cells ordering/labels.
- Inherited: spot-run your stage-1 suite against stage-2 once it exists — regression must be zero.

PHASE 2 (on implementer handoffs): re-run everything at the named revision, then the official harness — `D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 2 --out <NEW dir>` and the same with `--mode isolated` (each run needs a fresh out dir; suggest `D:\WED Dark factory\evidence\harness\s2-runN`). Report verdict CONFIRMED or a numbered findings list citing exact clauses/revisions. Baseline to beat: stage-1's 225 own checks + official 120/120 — a falling total on added surface needs explaining.

RULES: you never repair product code; findings route to the author via coordinator. Check the real diff/commits incl. test bodies, not summaries. Message budget is real — one phase-1 ready notice and one verdict message; no status chatter.

DONE = verdict message to the room addressed to @mukeshkbj/tk-coordinator naming exact checked SHA, every command + counts + durations, held-open items. Then end your turn.
