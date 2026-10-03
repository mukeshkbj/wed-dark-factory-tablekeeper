# Stage-4 Acceptance Gate — FROZEN

**Frozen product revision:** `579f39c` (`stage-4/` tree; verifier evidence commits do not alter product code)
**Verifier-confirmed evidence revision:** `7270d14` (re-run evidence: `2e3bf6f`)
**Coordinator isolated run revision:** `2e3bf6f`
**Recorded at:** 2026-10-03
**Recorded by:** operator, using the independent verifier verdict and the coordinator-required isolated harness run

## Verification evidence

| Check | Result | Reference |
|---|---|---|
| Coordinator official harness, isolated | **Stage-1 120/120; stage-2 25/25; stage-3 7/7; stage-4 6/6**; `state: completed`, `highest_contiguous: 4` | `evidence/harness/s4-run2-coordinator-isolated/report.json` (run_id `bbcc81d3f5874dd3b5c80c77de7fe7cf`, revision `2e3bf6f`) |
| Verifier verdict | **CONFIRMED** for product tree `579f39c` | `7270d14`; re-run evidence commit `2e3bf6f` |
| Official harness, verifier host + isolated | Stage-1 120/120; stage-2 25/25; stage-3 7/7; stage-4 6/6 in both modes | `evidence/harness/s4-phase2-host/`, `s4-phase2-isolated/`; gate re-run `evidence/harness/s4-gate-host/`, `s4-gate-isolated/` |
| Independent combined API suite | **862/862 PASS**, 0 5xx | `verification/stage-4/README.md`; verifier evidence at `62a9439` |
| Upgrade continuity | **62/62 PASS** across stage-1/2/3/4 exports and round trips | `verification/stage-4/upgrade_checks.py`; verifier evidence at `62a9439` |
| Hardened deployment | **5/5 PASS** | `verification/stage-4/README.md`; verifier evidence at `62a9439` |
| Inherited browser contract | **82/82 PASS**; stage-4 adds no screens | `verification/stage-4/ui_checks.py`; verifier evidence at `62a9439` |

The coordinator harness report records `started_at` `2026-10-03T05:43:24.896620+00:00` and `finished_at` `2026-10-03T05:44:25.530662+00:00`.

## Product revision and gate trail

- `c4c09af` — stage-4 scaffold copied from frozen stage-3.
- `3e3250a` — engineer: closure replans and series amendments.
- `579f39c` — experience: applied-replan UI continuity check and session record; accepted product tree.
- `a914744` / `b0b0fe6` — verifier stage-4 matrix/suites and verifier-side fixture/check corrections.
- `62a9439` — verifier clean combined run evidence; 862/862 API checks passed.
- `88eb456` / `7270d14` — official host+isolated evidence and CONFIRMED verdict at product tree `579f39c`.
- `2e3bf6f` — official gate re-run evidence; host and isolated both passed stages 1–4 at the same product tree.
- Coordinator-required isolated harness run at `2e3bf6f` passed all stages; report committed with this freeze record.

The stage-4 product tree is unchanged between `579f39c` and `2e3bf6f`; later commits add verifier/evidence artifacts only.

## Held open / packaging

- This gate freezes the product tree at `579f39c`; future product changes require an explicit reopening and re-verification.
- The official final `--all --mode isolated` sweep and clean-clone validation remain packaging gates and are not claimed here.
- `room.json` must be exported from the real BAND room by the operator; do not fabricate it. Run the official offline harness `check` after that export.
- The reviewed inherited-UI screenshots from the stage-4 gate are included under `evidence/ui-s4-gate/`. Older untracked screenshot sets under `evidence/ui-s3/`, `evidence/ui-s3-phase2/`, `evidence/ui-s3-gate/`, and `evidence/ui-s4/` are redundant and remain outside this freeze commit.
- The verifier suite is broad but cannot guarantee hidden judging tests; see `verification/stage-4/matrix.md` for coverage limits.

## Freeze rule

`stage-4/` is frozen at product revision `579f39c`. No product-code changes should be made without a coordinator reopening record and a fresh independent gate.
