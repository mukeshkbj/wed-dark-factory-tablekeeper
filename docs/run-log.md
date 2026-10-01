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
| 1 | pending | pending | Coordinator gate 2026-10-02: `harness run --stage 1` @ `811cf5f` → **stage 1 pass (claimed 1)**, stage-2 overshoot correctly fails (no UI). Verifier phase-2 pending — dispatched `docs/handoffs/s1-verifier-phase2.md`. |

## 2026-10-02 coordinator notes

- Seat runtime recovery: all four seats' jamd workers were stopped after app restart. `band attach` bound this session's PID to the room host session (`presence=live`); `band restart` respawned engineer/experience/verifier `devin acp` runtimes (Connected again). Coordinator scope worker stayed stopped → `send`/`inbox`/`chat` CLI ops unavailable this turn; dispatch delivered via the ACP turn response instead (posts to the room, @mention wakes verifier).
- Coordinator independent check run of `verification/stage-1/checks.py` @ `811cf5f` (local `python src/server.py`): ~57 fails, nearly all **probe defects** — `utc_local()` emits off-grid minutes (spec §4: grid is `slot_minutes` steps **from opening time** → 422 `not_on_slot_grid` correct); `C-AV-6` puts a raw space in the request-target; `C-DST-3` books an interval that truly overlaps the `02:30` fold-night booking → 409 correct per §1; `sec_concurrency` raised StopIteration. Filed for verifier to fix probes + re-run.
- Engineer reported (room, 07:47Z): handoff sent to verifier (msg `0b1c1648`), 216/225 verifier checks at `d41f587`, fold-night overlap flagged for ruling → ruled: 409 is correct (absolute-interval overlap).
