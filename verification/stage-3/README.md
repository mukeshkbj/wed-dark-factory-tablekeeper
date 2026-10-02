# tk-verifier — stage-3 verification suite

Independent, spec-derived checks for Tablekeeper stage 3
(`D:\tk-official\tablekeeper\spec\stage-3.md` @803560d), plus the complete
inherited stage-1 + stage-2 suites.

## Layout

| File | Purpose |
|---|---|
| `matrix.md` | Clause-by-clause requirement matrix (E/H/P/T/S/X/B/M/D) mapped to check ids |
| `checks.py` | API/domain suite — inherits stage-2 (and thus stage-1) verbatim, adds ~290 stage-3 checks |
| `upgrade_checks.py` | X-section: stage-1/stage-2 exports → stage-3 import; series adoption on imports; stage-3 round-trip |
| `ui_checks.py` | Thin shim — delegates to the stage-2 UI suite (stage-3 adds no screens, R3-15 / D-5) |

## Running

```sh
# everything (inherited + stage-3), against a running stage-3 service
python checks.py --base-url http://localhost:8096
python checks.py --base-url ... --s3-only           # stage-3 sections only
python checks.py --base-url ... --inherited-only    # stage-1+2 regression
python checks.py --base-url ... --hardened          # TK_HARDENED=1 instance probes
python checks.py --base-url ... --only series       # section-name filter

# upgrade legs need three services: s1, s2, s3 code on separate ports
python upgrade_checks.py --s1-url :8091 --s2-url :8092 --s3-url :8096

# browser contract (inherited suite verbatim)
D:/tk-official/.venv/Scripts/python.exe ui_checks.py --base-url :8096
```

## Conventions

Same as stage-2: `C3-<section>-<n>` check ids, `expect`/`check_status`/
`note` helpers, every call has a hard timeout, a hang or exception counts as
failure, exit code 1 on any FAIL or 5xx/conn-error. Fixtures extend the
stage-2 `fixture_combo()` with `manager_user_ids` (R3-2): `u_ada` manages all
restaurants, `u_bob` is the non-manager probe.

## Methodology note — one suite per service instance

Suites mutate global service state via `/_test/reset` and `/_test/import`.
NEVER run two checkers (or manual probes) against the same port
concurrently — resets wipe tokens mid-run and produce symmetric,
nondeterministic failures in BOTH runs (observed 2026-10-02: concurrent
inherited-regression + upgrade runs each reported phantom 401/404s; both
passed clean when re-run sequentially). If two suites must overlap, give
each its own service process and port.

Also beware SO_REUSEADDR double-binds on Windows: `netstat -ano | grep
LISTENING` the target port first — a second python server CAN bind an
already-listening port and requests will round-robin between them.
Confirmed on :8091 (two stale listeners) and :8099 (one stale + one
hardened — the first hardened probe measured the stale instance).

## Phase-1 smoke results (HEAD `d9d04ba`, clean ports)

| Suite | Target | Result |
|---|---|---|
| `checks.py --s3-only` | :8096 (stage-3) | 287/287 PASS, 0 5xx, ~703s |
| `upgrade_checks.py` | :8097 s1, :8098 s2, :8096 s3 | 38/38 PASS, ~91s |
| `checks.py --hardened` | :8105 (`TK_HARDENED=1`) | 5/5 PASS |
| D-2 verbatim copy | `git diff 5be5343 c23f857 -- stage-3` | pure additions, identical content |

Inherited-only and inherited-UI runs: see evidence trail / phase verdict.
