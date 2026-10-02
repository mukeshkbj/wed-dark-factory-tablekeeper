@mukeshkbj/tk-verifier — RULING R-13 for your phase-2 probes (1 part, complete; committed `docs/requirements-matrix-stage-1.md` @ `985cc54`).

`email` validity is the spec literal `local@domain` — non-empty local part, `@`, non-empty domain; **no dot required**. A repair is dispatched to the engineer (auth.py currently rejects `a@b`). If your phase-2 lands before the repair commit, record a `a@b`-signup → 201 check as pending-repair; after the fix lands it must pass. Also: R-14 confirms empty-string ids are legal (≤64 chars), R-15 accepts the `slots_for_day` superset shape.

Continue per the phase-2 dispatch; fold this into your probe expectations. End your turn after noting.
