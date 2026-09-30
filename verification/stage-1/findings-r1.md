# Stage-1 gate round 1 — findings (verifier: tk-verifier, SWE-2 High)

Candidate revision under review: `695a903` (stage-1 candidate HEAD).
Verdict this round: **REJECTED** — two production defects; all other official-suite
failures trace to defect 1.

## Evidence collected

| Run | Command | Result |
|---|---|---|
| Official suite vs live host service (port 8137) | `pytest tablekeeper/test/stage_1 -p harness.plugin --base-url http://127.0.0.1:8137 -q` | 60 failed / 60 passed |
| Official harness (container), run 2 | `python -m harness run --track tablekeeper --repo .. --stage 1 --out evidence/harness/s1-run2` (PYTHONUTF8=1) | 9 passed / 29 failed / 82 errors; errors = host-side ZoneInfoNotFoundError (harness venv lacked tzdata — fixed env-side, harness/tests untouched) |
| Official harness run 1 | same, without PYTHONUTF8 | charmap crash during report write |
| Verifier independent suite vs live service | `python verification/stage-1/checks.py` | 162/168 pass; 6 failures all verifier probe bugs (fixed at 9c2b9d9) — zero product failures |
| Keep-alive repro | single http.client.HTTPConnection: login then POST /reservations | POST -> 422 missing field: restaurant_id (replayed login body) |

## Defect 1 — CRITICAL — keep-alive body replay
`stage-1/src/server.py` `Handler._read_body` caches `self._body`; the handler instance
outlives one request on a persistent connection, so later requests on the same
connection parse the first request's body. `_handle`'s drain reads the stale cache.
Impact: every connection-reusing client (httpx, browsers via fetch keep-alive, real
API clients) corrupts all requests after the first on each connection.
Official failures attributable: ~55/60 (all "missing field:", KeyError 'reference',
expected-401-got-200 login, the 10-client race {422:10}).
Verifier regression check added: `C-KA-1` (commit 9c2b9d9).

## Defect 2 — HIGH — seeded reference pattern relaxation
Commit `4ebb124` accepted any seed reference <=64 chars. Official test
`test_reset_rejects_invalid_reservation_references` requires 422 for `x`,
`lower01`, `TOO-LONG-WITH-DASH`. Spec: reference is 6-12 chars of A-Z0-9; the 64-char
limit covers opaque ids only. Coordinator ruling recorded in `695a903` conflicts with
the official suite and must be reverted in `stage-1/src/fixtures.py`.

## Verifier-side corrections (commit 9c2b9d9)
- C-MV-7a probe gained `"table_id":"t_1"` (previously stayed on a free table -> 201 correct)
- C-CON-1/2 use `valid_grid_slot()` to keep race slots inside r_now opening hours
- New C-KA-1 keep-alive regression check

## Pending
Recheck on repair commit: full official suite + independent suite + isolated harness.
