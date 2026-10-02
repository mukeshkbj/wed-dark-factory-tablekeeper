# Stage-2 Acceptance Gate — FROZEN

**Frozen revision:** `ee28d6b` (HEAD at time of freeze)
**Accepted product revision:** `5be5343` (`stage-2/` tree; `ee28d6b` adds verifier evidence only)
**Frozen at:** 2026-10-02
**Recorded by:** `mukeshkbj/tk-coordinator`

## Verification evidence

| Check | Result | Reference |
|---|---|---|
| Coordinator official harness, isolated | **stage-1 120/120 pass; stage-2 25/25 pass**, `state: completed`, `mode: isolated` | `evidence/harness/s2-run7-coordinator-isolated/report.json` (revision `ee28d6b`, run_id `78813119880a4836a80ab2b43b85e043`) |
| Verifier final verdict | **ACCEPTED** @`5be5343` | commit `ee28d6b`, `verification/stage-2/phase-verdict-b424a8b.md` follow-up |
| Verifier own API suite | **350/350 PASS**, 0 FAIL, 0 5xx | `verification/stage-2/checks.py`, evidence recorded in verdict |
| Verifier own UI suite | **82/82 PASS**, including `U-GRID-6a/b` OR-selector guards | `verification/stage-2/ui_checks.py`, evidence recorded in verdict |
| Upgrade continuity | **19/19 PASS** | `verification/stage-2/upgrade_checks.py` |
| Reference-model replay | **3 x 500 ops, 0 disagreements** | `verification/stage-2/model.py` |
| Hardened mode | **5/5 PASS** | verifier verdict |
| Author unit tests | **127/127 OK** | `python -m unittest discover -s stage-2/tests` |
| Official harness, verifier host + isolated | **stage-1 120/120; stage-2 25/25** in both modes | `evidence/harness/s2-run5-postfix/report.json`, `evidence/harness/s2-run6-isolated/report.json` |

## Repair gate

Initial verifier gate @`b424a8b` was **REJECTED** on blocker S2-1: the hidden
`no-slots` element preceded `availability-grid` in DOM order, so the official
OR-selector wait resolved the hidden element and every successful search timed
out. `5be5343` repairs the defect by detaching the inapplicable element from the
DOM; verifier re-ran the focused guards, full suites, and official harness and
issued ACCEPTED.

## Delta after accepted product revision

`ee28d6b` contains verifier evidence and a verifier-side test correction only;
`stage-2/` remains the accepted product tree from `5be5343`. The coordinator
isolated harness ran at `ee28d6b` and passed both inherited stage-1 and stage-2
checks. Stage-3 overshoot correctly fails.

## Governance trail (room `9bf93138-25b0-431d-aa62-4a3dbca30155`)

- `9eb8381` coordinator: requirements matrix, run plan, seat handoffs
- `430abbd` engineer: stage-2 scaffold from frozen stage-1
- `14936ad` engineer: combined tables, upgrade import, UI route plumbing
- `b424a8b` experience: combinable fixtures, demo seed, browser UI
- `8a9c22b` verifier: spec-derived matrix/checks; REJECTED on S2-1
- `5be5343` experience: S2-1 repair
- `ee28d6b` verifier: S2-1 verified; stage-2 ACCEPTED

## Held open

- Hidden judging tests exceed the shipped sample; verifier matrix F-1/F-4/F-5
  observations stand.
- W-V-* visual clauses remain screenshot-captured human-review observations.
- Stage-3 overshoot correctly fails; stage-3 work starts from this frozen base.
- Untracked preliminary harness outputs under `evidence/harness/s2-run1/` and
  `s2-run3-isolated/` are retained locally but are not acceptance evidence.

## Freeze rule

`stage-2/` is frozen: no further product-code changes without a coordinator
reopening record. Fixes discovered later must target a new revision and be
re-verified against this gate.
