# verification/stage-4 — independent verifier suite (stage-4)

Spec-derived black-box checks for the Tablekeeper stage-4 surface:
closure replans (preview/apply), applied closures as occupancy, series
amendments, upgrade/import continuity, and concurrency/atomicity —
plus the COMPLETE inherited stage-1+2+3 suites run verbatim.

Sources (authoritative order):
1. `D:\tk-official\tablekeeper\spec\stage-4.md` — official spec text
2. `docs/requirements-matrix-stage-4.md` — coordinator rulings R4-1..R4-24
   (claim list to falsify, not gospel)
3. Inherited specs via the loaded s1/s2/s3 check modules

## Files

| File | Role |
|---|---|
| `checks.py` | API suite: RP (preview), RA (apply/closures), SA (series amend), CON (concurrency), HRD (hardened). Inherits s1+s2+s3 sections via dynamic load. |
| `upgrade_checks.py` | X legs: s1/s2/s3 exports -> s4 import; s4 round-trip preserving plans+closures+series; bad-import atomicity. Needs 4 running services. |
| `ui_checks.py` | R4-24/D-5 shim: runs the full stage-2 browser contract against the s4 surface (needs playwright; use the harness venv). |
| `matrix.md` | Clause -> check-id coverage map. |

## Usage

```bash
# full suite (inherited s1+s2+s3 plus all stage-4 sections)
python verification/stage-4/checks.py --base-url http://localhost:8096

# inherited regression only (350 s1+s2 + 287 s3 checks)
python verification/stage-4/checks.py --base-url ... --inherited-only

# stage-4 sections only
python verification/stage-4/checks.py --base-url ... --s4-only

# a single section family
python verification/stage-4/checks.py --base-url ... --only sa_

# hardened instance probes (service started with TK_HARDENED=1)
python verification/stage-4/checks.py --base-url ... --hardened

# upgrade legs — needs s1,s2,s3,s4 services on their ports
python verification/stage-4/upgrade_checks.py \
    --s1-url http://localhost:8097 --s2-url http://localhost:8098 \
    --s3-url http://localhost:8099 --s4-url http://localhost:8096

# browser contract (playwright)
D:/tk-official/.venv/Scripts/python.exe \
    verification/stage-4/ui_checks.py --base-url ... --shots evidence/ui-s4
```

## Methodology notes (learned in earlier stages — kept deliberately)

- **Sequential suites only.** Mutating suites racing on one instance caused
  phantom upgrade failures in s3. One suite per instance; suites may run in
  parallel only against *separate* ports.
- **Verify the listener before trusting a port.** Windows `SO_REUSEADDR`
  allows double-binds; `netstat -ano | findstr LISTENING` first, or probe
  `/health` and confirm the expected surface.
- **Absolute instants for replans.** `from`/`to` carry explicit UTC offsets
  (`iso()`), while bookings stay naive local (`local()`), matching the spec.
- **Half-open windows.** Boundary bookings (end==from, start==to) are
  excluded from the considered set; boundary slots keep closed tables in
  availability until `to`.
- **Coherence over assumption in the stale matrix.** Instead of asserting a
  given write MUST bump restaurant_revision, the matrix probes the revision
  via a fresh empty-window preview and requires apply coherence
  (bumped -> stale_plan; not bumped -> not stale_plan).
- **Non-UTF8 hazard.** All files are UTF-8; heredoc/paste paths have
  mangled em-dashes before — `python -c compile(..., 'exec')` with
  `encoding='utf-8'` is the syntax gate, not plain `ast.parse`.
- **Late-day flakiness.** Fixtures derived from `now()` are clamped to a
  22:45 start; checks that need *later* slots probe whole windows or
  skip-with-note rather than assume a grid point exists.

## Check-id conventions

`C4-<SECTION>-<n><letter>` — e.g. `C4-RP-7a`. Upgrade checks use
`X-<leg>-<n>` (`s1|s2|s3|s4` legs). Failures print as `FAIL <cid> - detail`;
summary line counts checks, fails, and 5xx/connection errors separately.

## Phase-1 smoke results @ `579f39c` (stage-4 impl)

| Stream | Result |
|---|---|
| `--s4-only` (all 17 stage-4 sections) | 224/224 PASS, 0 5xx, ~800s |
| `upgrade_checks.py` (s1+s2+s3+s4) | 62/62 PASS, ~140s |
| `--hardened` (`TK_HARDENED=1`) | 5/5 PASS |
| `ui_checks.py` (inherited s2 browser contract) | 82/82 PASS |
| Full combined run (inherited + s4) | 862/862 PASS, 0 5xx, 2337s (clean re-run incl. late-day fixture fixes) |

All phase-1 failures observed were verifier defects (tuple unwrap,
stale tokens after mid-check resets, `err_code` shape, non-existent
`GET /series` list route, `series_id` vs `id`, empty-collection
normalisation in export round-trip). Zero confirmed product findings.
