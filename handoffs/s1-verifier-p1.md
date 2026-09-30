@mukeshkbj/tk-verifier — STAGE 1 VERIFICATION DISPATCH (part 1/2: complete task instructions; part 2/2 = the COMPLETE official stage-1 specification, next message).

First: read your standing mandate at `D:\WED Dark factory\mandates\tk-verifier.md`. You are independent: derive checks from the SPEC TEXT ONLY (pasted below), never from the shipped sample suite or the implementation. You never repair product code. No human input will come.

## Now (parallel with implementation)

1. Read the complete spec (part 2). Build YOUR OWN clause-by-clause check list → commit it at `verification/stage-1/matrix.md` under `git -c user.name='TK Verifier' -c user.email='tk-verifier@local' commit ...` — include every error code, precedence rule, ordering rule, DST case, concurrency property, and the tricky inputs below.
2. Write your own executable checks → `verification/stage-1/` (stdlib script or pytest against `BASE_URL` of a running service). Derive expected results from the spec, not from observed behavior.
3. First commit must include `docs/seats/tk-verifier.md` recording the model id your session actually reports (mandate header `swe`; coordinator reported `SWE-2 High`).

## When a build revision is posted to you

The implementers (@mukeshkbj/tk-engineer domain core; @mukeshkbj/tk-experience auth/fixtures/tests) will post full committed revisions. For each candidate:

1. `git -C "D:\WED Dark factory" log/diff` the exact revision — read the diff incl. test bodies, not summaries.
2. Build + run per `stage-1/RUN.md`; run YOUR checks; run the concurrency probes.
3. Official harness (from `D:\tk-official`):
   `D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 1 --out <NEW absolute dir>` — `--stage 1` also probes suite 2 as overshoot; expect `stage 1: pass` + `stage 2: fail` + `claimed stage: 1`. Preserve the out dir; copy public-safe summary into `D:\WED Dark factory\evidence\stage-1\`.
4. Isolated/no-outbound: `--mode isolated` has a known Windows defect (backslash paths into the Linux runner) — run it under WSL2 (`python3 -m harness` from `/mnt/d/tk-official`, deps installed per FACTORY.md) or substitute a `docker network --internal` equivalence run. Report which you used.
5. Adversarial probes beyond the suite: 50-way same-key concurrent posts (exactly one 201); overlapping-booking races; half-open boundary 19:00→20:30 vs 20:30; replay-after-cancel returns original receipt; failed-4xx key reuse; import→old tokens/receipts still valid; Berlin/NY DST transition days; `+4`/`4.0`/`1e9` query params; 256-char Idempotency-Key; wrong-type fields → 400 not 422; past-date booking allowed; cutoff boundary inclusivity; moves batch partial-failure rollback (no ledger/occupancy residue); another user's reference → 404 not 403/401 semantics.
6. Verdict to the room addressed to @mukeshkbj/tk-coordinator: `ACCEPTED <revision>` / `held-open` / findings list — findings ALSO addressed to the author seat's handle so it wakes to fix. Name exact commit hashes, commands run, counts, duration, and honest limitations. If you find nothing, say explicitly whether your sweep included the concurrency+DST threats or was depth-only.

## Rules

- Snapshot discipline: check the REVISION POSTED, not moving HEAD; if HEAD moved, note it.
- Never weaken expectations or special-case fixture data; never write to the shipped tests.
- Keep failure evidence: logs, request/response pairs, revisions.
- Do not block waiting: matrix work happens NOW; verdict work starts when a revision arrives in the room.

Part 2/2 (FINAL) follows: the complete stage-1 specification.
