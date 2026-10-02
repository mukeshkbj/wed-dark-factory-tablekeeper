# Run log — scored run, room a80cdbce-db3b-4f69-a49f-d0b48119d581

Started 2026-10-01 by the single production dispatch (`dispatch.md`).

## Resolved model ids (mandate headers request `swe`)

| Seat | Mandate header | Session reports |
|---|---|---|
| tk-coordinator | `swe` | Devin ACP runtime; powered by SWE-2 High (resolved `swe` class) |
| tk-engineer | `swe` | (recorded on its first commit) |
| tk-experience | `swe` | (recorded on its first commit) |
| tk-verifier | `swe` | SWE-2 High (recorded `verification/stage-1/README.md` @ `8771d7d`) |

## Stage gate record

| Stage | Accepted revision | Checks | Notes |
|---|---|---|---|
| 1 | `aae0226` (`stage-1/` tree `14c9e43`) | verifier CONFIRMED; official 120/120 isolated | Frozen — `docs/gates/stage-1-freeze.md`. |
| 2 | `ee28d6b` (`stage-2/` tree `5be5343`) | verifier ACCEPTED; coordinator official 120/120 stage-1 + 25/25 stage-2 isolated | Frozen — `docs/gates/stage-2-freeze.md`. |
| 3 | `e5679e3` (`stage-3/` tree `d9d04ba`) | verifier CONFIRMED; coordinator official 120/120 stage-1 + 25/25 stage-2 + 7/7 stage-3 isolated | Frozen — `docs/gates/stage-3-freeze.md`. |

## 2026-10-02 coordinator notes

- Seat runtime recovery: all four seats' jamd workers were stopped after app restart. `band attach` bound this session's PID to the room host session (`presence=live`); `band restart` respawned engineer/experience/verifier `devin acp` runtimes (Connected again). Coordinator scope worker stayed stopped → `send`/`inbox`/`chat` CLI ops unavailable this turn; dispatch delivered via the ACP turn response instead (posts to the room, @mention wakes verifier).
- Coordinator independent check run of `verification/stage-1/checks.py` @ `811cf5f` (local `python src/server.py`): ~57 fails, nearly all **probe defects** — `utc_local()` emits off-grid minutes (spec §4: grid is `slot_minutes` steps **from opening time** → 422 `not_on_slot_grid` correct); `C-AV-6` puts a raw space in the request-target; `C-DST-3` books an interval that truly overlaps the `02:30` fold-night booking → 409 correct per §1; `sec_concurrency` raised StopIteration. Filed for verifier to fix probes + re-run.
- Engineer reported (room, 07:47Z): handoff sent to verifier (msg `0b1c1648`), 216/225 verifier checks at `d41f587`, fold-night overlap flagged for ruling → ruled: 409 is correct (absolute-interval overlap).

## Stage-1 phase-2 verifier verdict — ACCEPTED @ 811cf5f (2026-10-01)

Verifier commit `8d1a524` (probe fixes + `verification/stage-1/phase2-verdict.md`).
Coordinator-verified evidence:

- Independent suite: 225 checks, 0 FAIL, 0 5xx, exit 0 (~10.7s).
- Reference model: 1500 ops across seeds 7/13/42, 0 disagreements.
- Official harness isolated: `evidence/harness/s1-run6/report.json` —
  revision 811cf5f, mode isolated, stage-1 pass 120/120, state completed, ~91s.
- Stage-2 overshoot: fails on UI testids (expected — no stage-2 code).
- Adversarial read: RLock critical sections, per-user+path idempotency with
  original-body replay, G-10 whitespace keys via raw header bytes, atomic
  invalid imports, no plaintext passwords in export.

Held open: hidden judging tests may exceed shipped suite; matrix.md gaps marked.

### Conditional-acceptance repairs in flight (spec-literal hardening)
- R-12 (experience): fixtures.py — label optional, capacity/cutoff >= 0.
- R-13 (engineer): auth.py email regex — literal `local@domain`, no dot.
Post-repair verifier re-run at new HEAD required before final stage-1
accepted-SHA declaration.

## Stage-1 repairs landed — HEAD 7a79e89 (2026-10-02)

- `2793d5e` (TK Engineer, R-13): auth.py email regex -> literal local@domain;
  a@b / x@localhost signups 201; 108 unittests exit 0. Verified by coordinator.
- `7a79e89` (TK Experience, R-12): fixtures.py floor — label optional,
  capacity >= 0, cancellation_cutoff_minutes >= 0; extended negative email
  list; 109 unittests exit 0. Verified by coordinator (diff read).
- Seat note: engineer runtime had permission-prompt deadlocks earlier
  (operator resolved host-side); experience raced the R-12 reassignment and
  landed before stand-down arrived — engineer cancel notice sent (c24c8eaa).
- Verifier phase-3 re-verify dispatched (1c555bac): re-run checks + model +
  isolated harness at `7a79e89`; CONFIRMED closes stage-1 accepted SHA.

## Stage-2 gate — FROZEN @ ee28d6b (2026-10-02)

- Product revision `5be5343` accepted after S2-1 repair; `ee28d6b` adds verifier
  evidence only, so `stage-2/` is unchanged from the accepted product tree.
- Coordinator official harness `s2-run7-coordinator-isolated`: stage-1 120/120,
  stage-2 25/25, `state: completed`, `mode: isolated`; stage-3 overshoot fails
  as expected.
- Verifier final evidence: API 350/350, UI 82/82 including OR-selector guards,
  upgrade 19/19, model 3x500 ops clean, hardened mode 5/5, official host and
  isolated stage-2 25/25.
- Gate record: `docs/gates/stage-2-freeze.md`. Next stage: stage-3 dispatch.

## Stage-3 gate — FROZEN @ e5679e3 (2026-10-02)

- Product revision `d9d04ba` accepted: engineer `d8a0599` + experience
  `d9d04ba` on verbatim scaffold `c23f857`; verifier/evidence commits
  `113fc84` and `e5679e3` add no product-code delta.
- Coordinator official harness `s3-run1-coordinator-isolated`: stage-1 120/120,
  stage-2 25/25, stage-3 7/7, `state: completed`, `mode: isolated`; stage-4
  overshoot fails as expected.
- Verifier final evidence: independent API 637/637, upgrade 38/38, hardened
  5/5, inherited browser contract 82/82, official host and isolated stage-3
  7/7 with inherited stages green.
- Gate record: `docs/gates/stage-3-freeze.md`. Next stage: stage-4 dispatch.

## Stage-4 dispatch — ACTIVE (2026-10-02)

- Requirements matrix: `docs/requirements-matrix-stage-4.md` (R4-1..R4-24).
- Handoffs: `docs/handoffs/s4-engineer-task.md`, `s4-experience-task.md`,
  `s4-verifier-task.md`.
- Shared board: `#8` engineer, `#9` experience, `#10` verifier.
- Gate: verifier CONFIRMED plus coordinator-run official `--stage 4 --mode
  isolated` pass before `stage-4/` freezes.
