# Tablekeeper stage-4 demo runbook (3 minutes)

This is a local synthetic-data walkthrough of a table closure and the seating replan that preserves a confirmed guest's booking time and accepted terms. It uses the stage-4 service's fixture in `stage-4/src/fixtures.py` and the existing browser UI; stage-4 adds no new screens.

## Start a local service

From the repository root, in PowerShell terminal 1:

```powershell
Set-Location stage-4
python src/server.py
```

The service listens on `http://127.0.0.1:8080`. Keep it local for this demo. Test-control routes are enabled by default for the judge/test image; do not expose this default configuration to the public internet. `TK_HARDENED=1` disables every `/_test/*` route, including the reset used below.

In PowerShell terminal 2, from the repository root, load the synthetic fixture into the running process:

```powershell
$seed = python -c 'import json,sys; sys.path.insert(0,"stage-4/src"); import fixtures; print(json.dumps(fixtures.demo_seed()))'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/_test/reset -ContentType application/json -Body $seed
```

The fixture includes three restaurants in Berlin, New York, and Tokyo. For the walkthrough, use **Zum Anker** (`r_anker`) in Berlin. The demo manager is `ines@tablekeeper.test` / `ines-pass-789`; the guest account is `demo@tablekeeper.test` / `demo-pass-123`. These are deliberately synthetic local-demo credentials and must never be reused for a real service.

## Three-minute flow

### 0:00–0:35 — Show the guest promise

Open `http://127.0.0.1:8080/login` and sign in as the demo guest. The seeded confirmed reservation `ANK3R9` is at Zum Anker on **2026-10-02 at 19:30 Europe/Berlin**, party of four, initially assigned to **Chef's Counter** (`t_counter`).

### 0:35–1:30 — Preview the manager's closure plan

In PowerShell, log in as the seeded manager and capture the returned bearer token:

```powershell
$manager = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/auth/login -ContentType application/json -Body '{"email":"ines@tablekeeper.test","password":"ines-pass-789"}'
$token = $manager.token
```

Preview closure of Chef's Counter for the evening. The interval uses explicit Berlin offsets and half-open interval semantics:

```powershell
$headers = @{ Authorization = "Bearer $token"; 'Idempotency-Key' = 'demo-replan-preview-1' }
$closure = '{"table_id":"t_counter","from":"2026-10-02T18:00:00+02:00","to":"2026-10-02T23:00:00+02:00"}'
$plan = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/restaurants/r_anker/replans -Headers $headers -ContentType application/json -Body $closure
$plan | ConvertTo-Json -Depth 8
```

Point out the proposed assignment for `ANK3R9`. A preview does not apply changes; the response names the affected reservations, selected table IDs, move count, and plan ID.

### 1:30–2:10 — Apply atomically

Apply exactly the previewed plan:

```powershell
$applyHeaders = @{ Authorization = "Bearer $token"; 'Idempotency-Key' = 'demo-replan-apply-1' }
$applyUrl = "http://127.0.0.1:8080/restaurants/r_anker/replans/$($plan.plan_id)/apply"
Invoke-RestMethod -Method Post -Uri $applyUrl -Headers $applyHeaders -ContentType application/json -Body '{}'
```

The closure and changed assignments are applied atomically. `ANK3R9` keeps its guest, date, local time, party size, and accepted terms; its history records the reassignment. The plan ID can be used to trace the closure and history entry.

### 2:10–3:00 — Verify the existing guest surfaces

Return to the browser and sign in as `demo@tablekeeper.test` if needed.

1. On **Find a table**, choose Zum Anker, date `2026-10-02`, party size `2`, then Search. At `19:30`, Chef's Counter is unavailable for the closure, the table assigned to `ANK3R9` is occupied, and unaffected Window Two remains available.
2. Search `2026-10-03` and verify Chef's Counter is available at `21:00`; the closure is scoped to its interval.
3. Open **Your booking** or `/lookup`, enter reference `ANK3R9`, and verify the reservation remains confirmed and displays its new table assignment rather than Chef's Counter.

## Expected outcomes and limitations

- The manager preview is a proposal; occupancy and history change only after apply.
- The demo demonstrates one seeded reservation being reassigned. It does not claim production deployment, external users, revenue, or live restaurant data.
- Fixture dates are fixed at October 2–4, 2026; reset the fixture before each run. No public hosted demo URL is currently documented in this repository.
- The service's default test mode exposes `/_test/reset`, `/_test/export`, and `/_test/import`; use loopback only. Hardened mode disables those endpoints, and a production-safe seeded deployment is not part of this submission.

## Reproduce the focused check

With a local stage-4 service running on port 8080, the focused UI integration test performs the same reset, manager preview/apply, grid, and lookup checks:

```powershell
python stage-4/tests/test_stage4_ui.py --base-url http://127.0.0.1:8080
```
