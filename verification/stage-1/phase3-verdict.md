# Stage-1 Phase-3 Verdict — tk-verifier (delta re-verify)

**Verdict: CONFIRMED** — stage-1 accepted SHA is
`28b16f4c6000e7e3815aa15f2560a65e804989e2` (HEAD at verification time).
Product code is byte-identical to repair SHA
`7a79e89b4b0f502140782afc4b3dbe221ddb4f88`: `git diff 7a79e89..28b16f4 --
stage-1 verification` is empty; the only delta is coordinator docs
(`docs/handoffs/s1-verifier-phase3.md`, `docs/run-log.md`).

Scope: delta re-verify of the two spec-literal repairs landed after the
phase-2 freeze at `811cf5f`:
- `2793d5e` (R-13): `auth.py` email regex -> `^[^@\s]+@[^@\s]+$`
  (local@domain, no domain dot required).
- `7a79e89` (R-12): `fixtures.py` floor — table `label` optional (string
  when present), `capacity` integer >= 0, `cancellation_cutoff_minutes`
  integer >= 0.

## Evidence

| Leg | Command | Result | Exit |
|---|---|---|---|
| Independent spec-derived suite | `python verification/stage-1/checks.py --base-url http://127.0.0.1:8099` (service `PORT=8099 python stage-1/src/server.py` @ 28b16f4, CPython 3.14.7 + tzdata wheel) | **225 checks, 0 FAIL, 0 5xx/conn-errors** | 0 | 7.2s |
| Repair delta probes (ad hoc, urllib) | signup `a@b` -> 201; `x@localhost` -> 201; `@b.com`, `a b@c.com`, `a@`, `a@b@c` -> 422. `POST /_test/reset`: table missing `label` -> 204; `capacity:0` -> 204; `cancellation_cutoff_minutes:0` -> 204; `capacity:-1`, `cutoff:-1`, `label:7`, `capacity:"4"` -> 422 | **13/13 pass** | 0 |
| Reference-model replay | `python verification/stage-1/model.py --base-url http://127.0.0.1:8099 --ops 500 --seed 1` | **500 ops, 0 disagreements** (occupancy/outcome invariants held; one seed per dispatch — both repairs are validation relaxations) | 0 |
| Official harness, ACCEPTANCE | `python -m harness run --track tablekeeper --repo "D:\WED Dark factory" --stage 1 --mode isolated --out evidence\harness\s1-run7` (D:\tk-official\.venv, Docker 27.5.1) | **stage 1: pass, 120/120**, `mode: isolated`, `state: completed`, revision `28b16f4...` | 0 | ~90s |
| Official overshoot probe | same run, `--stage 2` inherited | fails on stage-2 surface — **expected**, no stage-2 code exists | — |

## Adversarial re-read of the repair diffs (diff, not summaries)

- `auth.py`: single-regex change only. `[^@\s]+` on both sides still rejects
  empty local (`@b.com`), whitespace anywhere (`a b@c.com`), trailing `@`
  (`a@`), and second `@` in domain (`a@b@c`) — confirmed live above, not just
  by reading. No other auth behavior touched.
- `fixtures.py`: `label` check moved behind `if "label" in t` (absent = ok,
  present non-string still 422); `capacity` floor lowered 1 -> 0;
  `cancellation_cutoff_minutes` split out of the >=1 group into its own
  >=0 check. `slot_minutes` / `reservation_duration_minutes` still >= 1.
  All failures still `FixtureError(422, "validation_failed")`; invalid
  fixture leaves state unchanged (re-verified by C-FX-1b in the suite).
- Zero-capacity tables are accepted by reset but can never satisfy a
  `party_size >= 1` booking — consistent with the R-12 floor ruling;
  availability math is unchanged.
- Test files changed in the same commits (`test_api.py`, `test_fixtures.py`)
  were read; they assert the new floor values, not just the old behavior.

## Caveats (unchanged from phase-2)

- Shipped suite is a documented portion of the judging set; hidden checks
  may exceed it. Matrix gaps remain as marked in `matrix.md`.
- Phase-3 ran the model at one seed (500 ops) per dispatch guidance;
  phase-2 covered 1500 ops across three seeds on the pre-repair code.
- Host Python here is 3.14.7 (phase-2 used a 3.12 venv); the isolated
  harness runs inside Docker on its own pinned base — judge-equivalent leg
  unaffected.

— TK Verifier, 2026-10-02
