# Stage-1 Phase-2 Verdict — tk-verifier

**Verdict: ACCEPTED** at commit `811cf5f8577943e2c3bd276c24537efa3572804d`
(master HEAD; tree frozen during verification, no product-code changes).

## Evidence

| Check | Command | Result | Exit | Duration |
|---|---|---|---|---|
| Independent spec-derived suite | `python verification/stage-1/checks.py --base-url http://127.0.0.1:8099` (service: `PORT=8099 python stage-1/src/server.py` @ 811cf5f, CPython 3.12 venv) | **225 checks, 0 FAIL, 0 5xx** | 0 | 10.7s |
| Reference-model replay | `python verification/stage-1/model.py --base-url http://127.0.0.1:8099 --ops 500 --seed {7,13,42}` | **1500 ops, 0 disagreements** (occupancy, outcome, idempotent-replay invariants held after every op) | 0 | ~3×25s |
| Official harness, host | `python -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 1 --out evidence\harness\s1-run5` | **120/120 pass** | 0 | 32.8s pytest / ~61s total |
| Official overshoot probe | same, `--stage 2` (s1-run5 + s1-run6) | fails on stage-2 UI testids — **expected**, no stage-2 code exists | 1 | — |
| Official harness, ACCEPTANCE | `python -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 1 --mode isolated --out evidence\harness\s1-run6` | **stage 1: pass, 120/120** in Docker isolated network | 0 | 21.8s pytest / ~91s total |

All run against the named commit; logs under `evidence/harness/s1-run5/` and
`s1-run6/`. Harness reports `state: completed`, `mode: isolated`, revision
`811cf5f...`.

## Probe defects fixed this round (checks were wrong, not the service)

1. `utc_local()` emitted arbitrary-minute times → all dependent creates hit the
   spec-correct `not_on_slot_grid` 422 and cascaded. Now snaps to the r_ops
   15-minute grid from opens 00:00 and clamps to the last valid start (22:45,
   since start+60min must be ≤ closes 23:59). ~50 downstream failures resolved.
2. `C-AV-6`: `" 4"`/`"4 "` were placed raw in the request-target (space breaks
   the request line). Now sent URL-encoded (`%204`, `4%20`) → server sees the
   non-plain-decimal value → correct 422 observed.
3. `C-DST-3`: booking 01:30 on `tb_1` while the 02:30 fold booking held
   00:30–02:00Z — absolute intervals overlap, so 409 was CORRECT. Fixture gains
   `tb_2` in `r_berlin`; the check now books tb_2 and still asserts
   `ends_at == 2026-10-25T02:00:00+01:00` (absolute duration across the fold).
4. `sec_concurrency`: `next(...)` raised StopIteration when no 201 existed,
   killing the section → guarded.
5. `model.py cmp_state`: passed a boolean into `agree()`'s status parameter —
   `True == 200` failed every state comparison. Fixed; rerun shows service and
   reference model agree on all 1500 ops.
6. Robustness: `assert st == 201` setup and raw `["slots"]` indexing replaced
   with recorded failures / `.get` so a single defect can't crash the suite.

`C-XP-4b` (state unchanged after invalid import) re-examined post-fix: passes —
the pre-import reservation now creates correctly and all five invalid imports
(400 malformed JSON; 422 wrong track / format_version 2 / missing state /
non-object state) leave state untouched.

## Adversarial review notes (committed diff read, not just summaries)

- `state.LOCK` (single RLock) wraps routing + handler → every check-and-act is
  one critical section; 25-thread same-key race produced exactly one 201 +
  24×200 identical bodies; 25-thread conflicting create produced exactly one
  winner (C-CON-1..3).
- `idempotency.execute` stores only sub-400 outcomes (failed writes free the
  key), scopes per user+key+method+path, replays return the stored original —
  byte-equal replay verified before AND after cancel, export/import, and moves
  amendment (C-IDM-7/9, C-XP-5d/5f2, C-MV-14).
- Whitespace-only `Idempotency-Key` read from raw header bytes (G-10) — the
  email parser would have stripped it (C-IDM-10).
- Error precedence verified: 400 malformed before auth, key-presence before
  idempotency, cutoff before per-field errors in moves (C-MV-10), input-order
  first-failure in batches, batch atomicity incl. rollback of earlier legal
  moves (C-MV-13/8).
- DST: spring-gap locals rejected `invalid_local_time` and omitted from slots;
  fall-back resolves to first occurrence (+02:00 Berlin, -04:00 NYC); absolute
  durations across the fold (C-DST-1..6).
- Export contains no plaintext passwords; import restores receipts/credentials;
  invalid imports are atomic no-ops; reset clears imported state.

## Held-open items / honest caveats

- The harness itself warns the shipped suite is a **portion** of the judging
  set; "accepted" here means: every spec clause my matrix covers passes, the
  reference model agrees on 1500 random ops, and the official stage-1 suite is
  green in the judge-equivalent isolated mode. Hidden checks can still surface
  defects — none are known.
- Matrix gaps remain as marked in `verification/stage-1/matrix.md` (e.g.
  malicious fixture shapes beyond the three mutated cases, extreme
  concurrency >25 threads).
- No service defects were found this round; nothing routed for repair.

— TK Verifier, 2026-10-02
