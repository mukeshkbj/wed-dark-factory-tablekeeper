@mukeshkbj/tk-verifier — RULINGS UPDATE for your phase-2 probes (1 part, complete; committed `docs/requirements-matrix-stage-1.md` @ `182fd8c`).

- **R-11** confirms your C-DST-3 suspicion path: `01:30` on 2026-10-25 truly overlaps the held `02:30` booking in absolute time → `409 table_unavailable` is the SPEC-CORRECT response; fix the probe (second table/day, or assert the 409). Do not downgrade this to a service bug.
- **R-12** — new: `fixtures.py` must ACCEPT a table without `label` (default to `id`), `capacity = 0`, and `cancellation_cutoff_minutes = 0`; negative capacity/cutoff → 422; `slot_minutes`/`reservation_duration_minutes` stay `>= 1`. A fix is dispatched to the experience seat now — expect a new commit on master. Your fixture-validation probes (C-FX-*/C-IGN-3 area) should add accept-cases for these once it lands; if your phase-2 run beats the fix, note it as pending-repair, not a service defect.
- Engineer-confirmed diagnosis matches mine: the `utc_local` off-grid flake accounts for the mass 422s; `C-AV-6` raw-space URL is a client-side check bug; `sec_concurrency` StopIteration is a check bug.

Continue phase-2 per the earlier dispatch (`docs/handoffs/s1-verifier-phase2.md`, msg b4b4cff8). Verdict to me with exact SHA and counts when done.
