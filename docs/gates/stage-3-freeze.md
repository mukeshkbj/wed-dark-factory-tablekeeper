# Stage-3 Acceptance Gate — FROZEN

**Frozen revision:** `e5679e3` (HEAD at time of freeze)
**Accepted product revision:** `d9d04ba` (`stage-3/` tree; `113fc84`/`e5679e3` add verifier artifacts only)
**Frozen at:** 2026-10-02
**Recorded by:** `mukeshkbj/tk-coordinator`

## Verification evidence

| Check | Result | Reference |
|---|---|---|
| Coordinator official harness, isolated | **stage-1 120/120; stage-2 25/25; stage-3 7/7**, `state: completed`, `mode: isolated`, `highest_contiguous: 3` | `evidence/harness/s3-run1-coordinator-isolated/report.json` (revision `e5679e3`, run_id `8e390f66bf89499fb505a7452620b6a9`) |
| Verifier final verdict | **CONFIRMED** for candidate product `d9d04ba` | room verdict `d44ae3b2-e812-414b-9712-5fa51fdb64a6`; evidence commit `e5679e3` |
| Verifier independent API suite | **637/637 PASS** — 350 inherited stage-1/2 checks + 287 stage-3 checks | `verification/stage-3/checks.py`, evidence recorded in verdict |
| Upgrade continuity | **38/38 PASS** — stage-1→3, stage-2→3, stage-3 round-trip | `verification/stage-3/upgrade_checks.py` |
| Hardened mode | **5/5 PASS** | verifier verdict |
| Inherited browser contract | **82/82 PASS** | `verification/stage-3/ui_checks.py`; stage-3 intentionally adds no new screens |
| Official harness, verifier host + isolated | **stage-1 120/120; stage-2 25/25; stage-3 7/7** in both modes | `evidence/harness/s3-phase2-host/report.json`, `evidence/harness/s3-phase2-isolated/report.json` |
| Author unit tests | **141/141 OK** reported after experience slice | `python -m unittest discover -s stage-3/tests` |
| Docker packaging | Build + `/health` smoke reported OK | engineer handoff at `d8a0599` |

## Gate trail (room `9bf93138-25b0-431d-aa62-4a3dbca30155`)

- `d1526a0` coordinator: stage-3 requirements matrix, run plan §12b, seat handoffs
- `1258e1a` coordinator: architecture adds `series`
- `c23f857` engineer: verbatim stage-3 scaffold from frozen stage-2 `5be5343`
- `d8a0599` engineer: policies, revisions/terms, history/decision, series, moves, import
- `d9d04ba` experience: `manager_user_ids` fixture validation and demo manager seed
- `113fc84` verifier: stage-3 independent suite and phase-1 smoke evidence
- `e5679e3` verifier: phase-2 gate evidence; CONFIRMED

## Held open

- Stage-4 overshoot correctly fails: official stage-4 probe `test_series_clock_time_can_be_changed` returns 404 because no stage-4 implementation exists yet.
- Hidden judging tests exceed the shipped sample; stage-3 reference-model replay remains a documented verifier coverage gap in `verification/stage-3/matrix.md`.
- `NOTE C2-FX-7c` records that a seed `party_size > capacity` is accepted for stage-1 floor parity; flagged, not failed.
- UI screenshot evidence under `evidence/ui-s3/` and `evidence/ui-s3-phase2/` remains untracked per evidence hygiene.
- Stale local listeners reported by the verifier were left running because ownership could not be verified; all acceptance evidence used clean ports.

## Freeze rule

`stage-3/` is frozen: no further product-code changes without a coordinator
reopening record. Fixes discovered later must target a new revision and be
re-verified against this gate.
