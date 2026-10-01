# TK Verifier — Stage 1 independent verification

Seat: `mukeshkbj/tk-verifier` (Devin ACP, `--agent-type review`).
Mandate: `mandates/tk-verifier.md`. Dispatch: room message e3c1ced8 +
committed copies `docs/handoffs/s1-verifier-part{1,2,3}.md`.

## Session model record (mandate header requested `swe`)
- Requested: `swe`
- Session-reported: `SWE-2 High` (runtime "powered by" banner). Reported honestly;
  no finer-grained id is exposed to this session.

## Sources of truth
- Requirements derived ONLY from the verbatim spec text
  (`docs/handoffs/s1-verifier-part2.md` §1–§7, `s1-verifier-part3.md` §8–§11,
  identical to `docs/handoffs/s1-spec-partA/B.md`).
- The shipped sample suite `D:\tk-official\tablekeeper\test\stage_1\` is NOT a
  requirement source and was not consulted for matrix/check derivation.
- `docs/requirements-matrix-stage-1.md` (coordinator seat) may be used as a
  cross-check for gaps only; it is not the derivation source.

## Files
- `matrix.md` — clause-by-clause requirement matrix (V-* ids) → check ids (C-*).
- `checks.py` — black-box HTTP check suite, stdlib only (urllib + threads).
- `model.py` — independent occupancy reference model + random-op replay driver.

## Running (Phase 2, against a named commit's running service)
```sh
python verification/stage-1/checks.py --base-url http://localhost:8080
python verification/stage-1/model.py --base-url http://localhost:8080 --ops 400 --seed 1
```
Both print PASS/FAIL lines and exit non-zero on any failure or error.
A hang is a failure: every request carries a hard timeout.

## Hygiene
- Only files under `verification/` are committed by this seat, with
  `-c user.name='TK Verifier' -c user.email='tk-verifier@local'`.
- `*.log` and `evidence/raw/` are gitignored — token-bearing material stays
  out of the repository.
