# TK Verifier — Stage 2 independent verification

Seat: `mukeshkbj/tk-verifier` (Devin ACP, `--agent-type review`).
Mandate: `mandates/tk-verifier.md`. Dispatch: room messages (stage-2 spec
parts A/B/C + task) with committed copies `docs/handoffs/s2-spec-partA.md`
(stage-2.md verbatim), `s2-spec-partB.md` / `s2-spec-partC.md` (stage-1.md
verbatim), `s2-verifier-task.md`.

## Session model record (mandate header requested `swe`)
- Requested: `swe`
- Session-reported: `SWE-2 High` (runtime "powered by" banner). Reported
  honestly; no finer-grained id is exposed to this session.

## Sources of truth
- Requirements derived ONLY from the verbatim spec text in the handoff files
  above (stage-2 spec + inherited stage-1 spec).
- The shipped sample suite `D:\tk-official\tablekeeper\test\stage_2\` is NOT a
  requirement source and was not consulted for matrix/check derivation.
- `docs/requirements-matrix-stage-2.md` (coordinator seat) used as a
  cross-check claim list only — treated as claims to falsify, not gospel.

## Files
- `matrix.md` — clause-by-clause requirement matrix (W-* ids) -> check ids.
- `checks.py` — black-box HTTP suite. Imports the COMPLETE stage-1 suite
  verbatim (inherited regression = zero tolerance) and adds stage-2 sections
  (`C2-*`): combinable fixture validation, `available_options`, `table_ids`
  create/patch/moves/cancel, combo idempotency, combo concurrency, hardened mode.
- `model.py` — independent occupancy reference model incl. combinable pairs +
  random-op replay driver (stage-1 model extended).
- `ui_checks.py` — Playwright browser probes (every `data-testid`, races,
  thief/dropped-response booking paths, combo cells, lookup, 375px sweep,
  upgrade-between-requests). Run with the harness venv interpreter:
  `D:\tk-official\.venv\Scripts\python.exe`.
- `upgrade_checks.py` — cross-service stage-1 -> stage-2 export/import
  continuity probes (tokens, references, pending idempotent retries).

## Running (Phase 2, against a named commit's running service)
```sh
python verification/stage-2/checks.py --base-url http://localhost:8080
python verification/stage-2/checks.py --base-url ... --inherited-only
python verification/stage-2/model.py --base-url http://localhost:8080 --ops 400 --seed 1
python verification/stage-2/upgrade_checks.py --s1-url http://localhost:8091 --s2-url http://localhost:8080
D:\tk-official\.venv\Scripts\python.exe verification/stage-2/ui_checks.py --base-url http://localhost:8080
```
All print PASS/FAIL lines and exit non-zero on any failure or error.
A hang is a failure: every request carries a hard timeout.

## Hygiene
- Only files under `verification/` are committed by this seat, with
  `-c user.name='TK Verifier' -c user.email='tk-verifier@local'`.
- `*.log`, screenshots (`evidence/raw/`) stay out of the repository —
  token-bearing artifacts are never committed.
