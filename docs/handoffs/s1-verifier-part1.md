@mukeshkbj/tk-verifier — STAGE 1 VERIFICATION DISPATCH [PART 1 of 3 — task; the complete official stage-1 spec follows verbatim in parts 2 and 3. You need all three parts.]

Before anything else: read your mandate file `D:\WED Dark factory\mandates\tk-verifier.md` — it governs this whole run. Record the model id your session actually reports in your first committed artifact; the mandate header requested `swe` — report the resolved value honestly.

TASK: independent verification of the stage-1 service the engineer and experience seats are now building in `D:\WED Dark factory\stage-1\`.

PHASE 1 (start immediately — no dependency on implementation): from the spec text pasted below ONLY — never from the shipped sample suite (`D:\tk-official\tablekeeper\test\stage_1\` is partial evidence, not the requirement):
1. Write your own clause-by-clause coverage matrix at `verification/stage-1/matrix.md` — every "must", limit, error code, precedence rule, ordering rule and worked example → numbered requirement. Mark gaps explicitly rather than implying coverage.
2. Author your own checks at `verification/stage-1/` (Python, your choice of runner — `requests`/`httpx`/`urllib` all fine against a running service): boundary conditions (half-open overlap edges, slot `start+duration == closes`, cutoff boundary `now == starts_at - cutoff`), invalid inputs (each error code incl. `1e9`/`4.0`/`+4` query params, non-bare `starts_at_local`, `party_size` as string/bool, 256-char idempotency key), concurrency (≥25 parallel identical bookings → exactly one 201 + one booking; parallel conflicting bookings → exactly one wins; conservation law: no table held twice at any instant), retries/replays (same key+body → 200 original; different body → 409; failed-4xx key reuse; replay after cancel returns ORIGINAL confirmed response), state transitions (cancel frees slot immediately; PATCH atomicity on failure), permissions (404-on-foreign everywhere, no existence leak), idempotency scoping (per-user, per-path), DST cases (Berlin 2026-03-29 gap + 2026-10-25 fold; New_York 2026-03-08 + 2026-11-01), export/import fidelity (tokens survive, receipts replay, destination wiped, invalid import leaves state), and reset determinism.
3. Where feasible, a tiny independent reference model for the occupancy invariant, replayed against random op sequences.

PHASE 2 (when an implementer handoff lands with a named commit): 
- Check out / confirm the stable revision; never test a moving tree — announce a snapshot window first.
- Run your checks against the running service, then the OFFICIAL harness yourself:
  `cd /d/tk-official && .venv/Scripts/python.exe -m harness run --track tablekeeper --repo "D:/WED Dark factory" --stage 1 --out <NEW abs dir>`
  (each run needs a fresh --out dir; existing dirs are refused)
- Then isolated mode: same command + `--mode isolated`. Windows isolated mode had issues in rehearsal — if it fails to run on native Windows, use the verified WSL path (kit + deps live under `~/tk` in WSL2; run `python -m harness run ... --mode isolated` there) and record exactly which path you used.
- The stage-2 overshoot probe will run as part of `--stage 1`; it SHOULD fail — that's expected and healthy.
- Read the actual committed diff including test bodies. Do your adversarial sweep: keys racing two operations, retries after partial failure, check-then-act splits, parser edge cases (a number arriving as `1000.00000000000000001`, boolean-vs-integer in JSON).
- Verdict to the room addressed to the coordinator seat (inspect `jam --profile default --session setup chat participants a80cdbce-db3b-4f69-a49f-d0b48119d581` for the exact handle): REJECTED / accepted-with-follow-up / ACCEPTED at an exact commit, each finding with requirement + reproduction + expected-vs-actual + severity, exact commands, exit codes, durations, counts. A check that errored counts as failure. A hang is a bug.

GIT: commit only files under `verification/` (and your matrix), per-command identity `git -c user.name='TK Verifier' -c user.email='tk-verifier@local' commit ...`. Never amend/squash/rebase; never touch another seat's files. Raw exports containing tokens must NOT be committed to the repo (`.gitignore` already excludes `evidence/raw/` — keep token-bearing dumps outside the repo or under that ignored path).

The complete official stage-1 spec follows in the next two parts.