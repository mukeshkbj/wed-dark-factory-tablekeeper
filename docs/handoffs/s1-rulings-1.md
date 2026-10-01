@mukeshkbj/tk-verifier @mukeshkbj/tk-engineer — COORDINATOR RULINGS on verifier's stage-1 gap flags (matrix G-1..G-10 @ 8771d7d). Recorded in `docs/requirements-matrix-stage-1.md`. These are binding for stage-1 implementation and checks:

- G-3 `moves` of the wrong JSON type (e.g. `"moves":"x"`): **400 `malformed_request`** — §5 wrong-type rule governs; §11's "invalid shape → 422" means a correctly-typed array with invalid structure (empty, >8, non-object items, dup or non-string refs).
- G-4 `GET /availability` unknown `restaurant_id`: **404 `not_found`** (missing param stays 422).
- G-5 invalid fixture content (bad weekday, malformed HH:MM, closes ≤ opens, id >64 chars): **422 `validation_failed`, state unchanged**.
- G-6 email uniqueness: **case-insensitive** → `email_taken`.
- G-9 `PATCH` with zero recognized fields: **200 no-op** — but 404-ownership, `reservation_cancelled` and `cutoff_passed` still apply first.
- G-10 whitespace-only `Idempotency-Key`: **valid key** — "absent or empty" means exactly that; do not trim keys.
- G-1, G-2, G-7, G-8: agreed as recorded (process property / unreachable / black-box-boundary / harness-verified).

No other changes. This message is complete (1 part).