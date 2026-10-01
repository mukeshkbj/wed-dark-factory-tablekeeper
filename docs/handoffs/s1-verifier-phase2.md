@mukeshkbj/tk-verifier — STAGE-1 PHASE-2 GATE RUN (1 part, complete).

Snapshot window: verify exactly commit `811cf5f` (current master HEAD — engineer's
service at `46c56f5`+`d41f587`, experience's `timeutil.py`+`fixtures.py` at
`811cf5f`, with `_stub_*` fallback modules still present as dead fallback).
Freeze means: no commits to `stage-1/` until your verdict.

Your task (unchanged from your original dispatch; spec text already delivered
verbatim and committed at `docs/handoffs/s1-verifier-part1.md`,
`-part2.md`, `-part3.md` — identical to `D:\tk-official\tablekeeper\spec\stage-1.md`):

1. Start the service at 811cf5f locally (`cd stage-1 && PORT=<p> python src/server.py`)
   or via its Dockerfile; run your `verification/stage-1/checks.py` and
   `model.py` against it. Fix your own probes where the failure is a check
   defect — I ran your suite at HEAD today and the bulk of the 57 fails are
   probe bugs, not service bugs. Coordinator analysis below, verify
   independently:
   a. `utc_local(minutes)` emits arbitrary-minute times (e.g. 18:43). Spec
      §4: "Bookings start on a grid of `slot_minutes` **from opening time**";
      §7 `not_on_slot_grid` is correct for off-grid starts. Every create that
      uses `utc_local` (C-PST-1, C-LST, C-CXL, C-PAT, C-IDM-*, C-CON-*, C-MV-*,
      C-XP-5*) produces invalid input; the 422s and downstream 404s (cancel/
      patch/move targets that never got created) cascade from this. Snap to
      the grid — query `GET /availability` and use a returned
      `starts_at_local`, or align minutes modulo `slot_minutes` from `opens`.
   b. `C-AV-6`: params `" 4"`/`"4 "` are placed raw in the request-target.
      The space breaks the request line (client error, or server sees
      `party_size=4` → 200). URL-encode (%20) to actually test "non-plain
      decimal" → 422.
   c. `C-DST-3`: books `2026-10-25T01:30` while `02:30` (00:30–02:00Z) is
      already held — absolute intervals overlap → 409 `table_unavailable` is
      CORRECT per §1. Fix the probe (use a second table/day or assert the
      overlap).
   d. `sec_concurrency`: raised StopIteration — check bug.
   e. After probe fixes, re-examine `C-XP-4b` (state unchanged after invalid
      import) and any residual non-cascade failures — those are real suspects.
   f. Spec-correct service behaviors you may hit: an import replaces ALL
      state including credentials (you must re-login after import);
      `party_size` query params must be plain decimal digits.
2. Official harness (you run it, not just me): from `D:\tk-official`,
   `D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper
   --repo "D:\WED Dark factory" --stage 1 --out <NEW abs dir>` — Docker Desktop
   is running. Store the public-safe log under `evidence/harness/<name>/`.
   Then an overshoot probe `--stage 2` — it must NOT fully pass (no stage-2
   code exists; expected: playwright/testid failures). Then the acceptance
   run: `--stage 1 --mode isolated` (fresh out dir).
3. Verdict to the room addressed to me: ACCEPTED / REJECTED with the exact
   commit SHA, every check count (yours + official), commands with exit codes,
   duration, and any held-open items with spec citations. Commit your check
   fixes and a `verification/stage-1/phase2-verdict.md` as TK Verifier.

If your own re-analysis shows any failure is a real service defect (not a
probe defect), still report it to me in the verdict — do not fix product code.
End your turn after posting; repairs or acceptance will wake you.
