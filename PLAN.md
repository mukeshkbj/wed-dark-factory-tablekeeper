# Dark Factory — Tablekeeper: Project Plan

**Event:** WeAreDevelopers × BAND — Dark Factory (lablab.ai), Sept 26 – Oct 5, 2026
**Track:** `tablekeeper` · **Seat runtime:** Devin CLI via BAND ACP · **Submission repo:** `D:\WED Dark factory`

## 1. Mission

Run a software factory in BAND Desktop: four agent seats in one room that turn
the official Tablekeeper specification into a verified, independently-buildable
service across four stages — then package the factory itself (mandates, room
log, measured evidence) as the submission.

Grading is automated and literal; most checks are hidden. The differentiator
is a factory that refuses to hand off non-conforming work.

## 2. Deliverables (submission checklist)

| Artifact | Status |
|---|---|
| Public GitHub repo (this folder) | scaffold committed |
| `mandates/` — 4 seat role files | ✅ written, generic, rehearsal-hardened |
| `dispatch.md` — one-shot run brief | ✅ final (handles, mandate read-first, model reporting) |
| `stage-1/` … `stage-4/` — Dockerfile, RUN.md, source, tests each | produced by the scored run |
| `plan.md` + `architecture.json` — room plan | coordinator seat |
| `docs/` — coverage matrix, DEMO-RUNBOOK.md | during run |
| `evidence/` — harness reports (public-safe) | during run |
| `FACTORY.md` — seats, decisions, measured time/tokens/cost | final |
| `room.json` — real Band export | final |
| `README.md` + `LICENSE` (MIT) | README ✅, LICENSE pending |
| lablab fields: title, description, tags, presentation PDF, demo | Oct 4–5 |

## 3. Seats

| Seat | Mandate | Owns | Forbidden |
|---|---|---|---|
| `tk-coordinator` | `mandates/tk-coordinator.md` | requirements matrix, plan, task board, acceptance, factory docs | product code |
| `tk-engineer` | `mandates/tk-engineer.md` | domain impl: state, availability, series, policies, replans, temporal, auth, Dockerfile | UI |
| `tk-experience` | `mandates/tk-experience.md` | stage-1 impl share, UI (s2+), manager screens, seed data, DEMO-RUNBOOK | domain core |
| `tk-verifier` | `mandates/tk-verifier.md` | spec-derived matrix, own checks, official harness, verdicts | product code |

All four are Band-owned ACP agents spawning `devin acp --model swe` (the
verifier adds `--agent-type review`), authenticated via `--runtime-auth
api_key`. Same model on every seat — differentiation is the mandate, not the
model. ACP seats cannot carry Band role files, so the dispatch tells each seat
to read its mandate file first; the file is both instruction and artifact.

## 4. Schedule — what actually happened

| Day | Workstream |
|---|---|
| **Sep 30** | ✅ Kit cloned `D:\tk-official` @ `803560d` · harness venv + chromium · mandates + dispatch committed · Docker up · **4 Devin ACP seats created + authenticated** · **Toy rehearsal complete: 4/4 stages accepted in ~2h**, stall recovery exercised |
| **Sep 30 – Oct 1** | **Scored run**: fresh room, seats' workdir = this repo, `dispatch.md` once — the only human input |
| **Oct 1–3** | Stage gates; fixes only via spec-grounded repair dispatches |
| **Oct 3–4** | Final `--all --mode isolated` (WSL path for the Windows harness bug), fresh-clone check, `room.json` export, FACTORY.md fill, video with room recording + PDF |
| **Oct 4–5** | Submit on lablab. Oct 5 23:59 PDT hard close |

## 5. Engineering requirements (from the official specs)

- Linearizable writes under 50 concurrent requests; no double-booking, ever
- Idempotency resolved before field validation; replays return the original
  response byte-for-byte; failed writes free the key
- Atomic batches (reservation-moves, series adoption, series amend, replan
  apply): all-or-nothing, no partial state
- IANA timezone/DST correctness; absolute durations; fall-back resolves to the
  first occurrence
- Exact error-code precedence (`malformed_request` for unparseable/wrong-type,
  `validation_failed` for in-range-but-invalid)
- Password hashing, owner isolation, no resource-existence leaks (404 on
  another user's reservation)
- Import/export preserves credentials, tokens, receipts, histories, opaque IDs
- Dated policies; immutable accepted terms; revision discipline
- **Stage 4**: bounded, deterministic, globally-optimal seating repair —
  minimize moves → unused seats → option-rank vector
- Single image ≤ 2 vCPU / 2 GiB; no runtime outbound network; `/_test`
  enabled in judge image, hardened demo mode disables it
- UI (stage 2+): real signup/login, search grid, responsive 375px+desktop,
  `data-testid` hooks, accessible focus/contrast, uncertain-vs-refused states,
  manager screens for policies/series/closure-preview-and-apply

## 6. Risk register (revised after rehearsal)

| Risk | Mitigation |
|---|---|
| Hidden tests ≠ visible samples | Verifier derives checks from spec text only; coverage matrix flags gaps |
| Ambiguous spec sentences | Coordinator records a ruling per ambiguity; spec wins over taste |
| Seat stalls / wake-loops | **Observed in rehearsal.** Mandates now require: act only on work-carrying messages; end turns; never poll in-turn; no keep-alives |
| Engineer context exhaustion | Short handoffs that still paste full spec; coordinator monitors context gauges |
| ACP auth missing on spawn | `devin auth login` once + `--runtime-auth api_key` + env allowlist on every template |
| Official harness `--mode isolated` broken on Windows | WSL2 harness path verified (`claimed 1` isolated on toy); fallback: `--network internal` equivalence run |
| Model id drift between requested and actual | Dispatch requires each seat to record its reported model in its first commit |
| Daemon/seat crash mid-run | Restart same seats + room; no new task/hints (rehearsal recovery proven) |
| Later stage breaks earlier contract | Spec-grounded fix + reverify affected folders; never retrofit backward |
| Time overrun | Stage-1 first; Oct 5 is buffer |

## 7. Definition of Done — per stage

- [ ] Verifier's spec-derived matrix shows every clause covered or flagged
- [ ] Official harness: stage N checks + all inherited suites pass
- [ ] Isolated/no-outbound execution verified (WSL harness or `--internal` equivalence)
- [ ] Next-stage overshoot probe fails as expected (where applicable)
- [ ] Folder frozen at a named commit; Dockerfile builds clean; RUN.md accurate
- [ ] Original commits preserved (no squash/amend/rebase)

## 8. Hard rules (from the official participant guide — disqualifiers)

- **Mandates must be generic** — no track vocabulary (endpoints, fields, error
  codes). Ours pass that test.
- **The scored run is hands-off** — the dispatch is the only human input.
- **Hand-built stage code doesn't count** — `stage-N/` commits must come from
  seats, traceable to the room log.
- **room.json** = the real room export, committed unchanged.
- **Video must show the Band room** — a handoff and the result.
- **Mandate files named after the seat as the room shows it**; each carries
  `Harness:` and `Model:` lines.
- **Stage claiming**: stage-N passes ≥half of every suite 1..N and must NOT
  pass all of suite N+1 (overshoot earns nothing).
- `harness check` runs gates 1+2+4 offline — run before every push.

## 9. Environment status

| Need | State |
|---|---|
| Kit `D:\tk-official` @ 803560d | ✅ cloned, pristine |
| Harness venv `D:\tk-official\.venv` | ✅ `python -m harness` works |
| WSL2 harness env (`~/tk` deps via `--user` pip) | ✅ isolated mode verified |
| Playwright chromium | ✅ installed |
| Docker Desktop 27.5.1 | ✅ running |
| Devin CLI 3000.11.3 | ✅ `auth login` done; `acp` seats verified end-to-end |
| Codex CLI 0.44.0 | ✅ installed, logged in (fallback runtime) |
| Band seats | ✅ tk-coordinator/engineer/experience/verifier live, api_key auth |
| Toy rehearsal | ✅ 4/4 accepted, evidence committed |

## 10. Open decisions

1. **Stack** — coordinator seat picks after reading spec §2 (recommendation:
   Python + SQLite WAL + vendored deps; `zoneinfo` covers the IANA contract).
2. **Public demo** — hardened deployment vs video-only.
3. **Model reporting** — `swe` requested; seats record actual resolved id on
   first commit (see dispatch).

## 12. Scored-run plan (active room plan)

Room `a80cdbce-db3b-4f69-a49f-d0b48119d581`, dispatched 2026-10-01 by
`dispatch.md` (hit the 10k message cap 2026-10-02; superseded by attempt-2
room `9bf93138-25b0-431d-aa62-4a3dbca30155`). Sequential stages, each through
the same gate:

1. **Stage 1** — ✅ FROZEN @ `aae0226` (`stage-1/` @ `14c9e43`; verifier
   CONFIRMED @`28b16f4` + test-only delta; official 120/120 isolated).
   Evidence: `docs/gates/stage-1-freeze.md`.
2. **Stage 2** — ✅ FROZEN @ `ee28d6b` (`stage-2/` product revision
   `5be5343`; verifier ACCEPTED + coordinator official 120/120 stage-1 and
   25/25 stage-2 isolated). Evidence: `docs/gates/stage-2-freeze.md`.
3. **Stage 3** — ✅ FROZEN @ `e5679e3` (`stage-3/` product revision
   `d9d04ba`; verifier CONFIRMED + coordinator official 120/120 stage-1,
   25/25 stage-2, 7/7 stage-3 isolated). Evidence:
   `docs/gates/stage-3-freeze.md`.
4. **Stage 4** — ACTIVE (this room): closure replans + series amendments;
   no new screens required. Plan below in §12c.
5. **Final** — `--all --mode isolated`, clean-clone check, offline
   `harness check`, FACTORY.md fill, final report.

### 12a. Stage-2 run plan (completed)

Source spec: `D:\tk-official\tablekeeper\spec\stage-2.md` (inherits all of
stage-1). Clause matrix: `docs/requirements-matrix-stage-2.md` (rulings
R2-1..R2-15). Contract deltas vs stage-1: `combinable` fixture field,
`available_options` in slots, `table_ids` on create/patch/moves/responses,
browser UI on 4 routes, stage-1→stage-2 export upgrade.

1. **tk-engineer** — copy `stage-1/` → `stage-2/` verbatim (no pycache);
   extend API: `table_ids` storage canonicalised in `combinable` order,
   `available_options`, combination error table (`combination_not_allowed`,
   per-member `table_unavailable`, summed `party_exceeds_capacity`), PATCH +
   moves with sets, transfer.py accepting stage-1-shaped export state
   (`table_id` → `table_ids` normalise), static-UI route plumbing
   (`/`, `/signup`, `/login`, `/lookup` + assets from `stage-2/ui/`),
   hardened `/_test` disable mode, Dockerfile/RUN.md updated.
2. **tk-experience** — `fixtures.py` `combinable` validation + demo seed
   with a declared pair; the entire browser surface `stage-2/ui/` (routes,
   testids U4–U8, combo cells C5, search-generation guard, booking lifecycle
   with minted-on-open idempotency key, `booking-uncertain` retry, 375px +
   desktop, warm hospitality direction — no external assets).
3. **tk-verifier** — own spec-derived stage-2 matrix + checks
   (`verification/stage-2/`), incl. Playwright UI probes beyond the shipped
   samples; then official harness `--stage 2` and `--mode isolated`;
   verdict CONFIRMED/HELD. Never repairs product code.
4. **tk-coordinator** — matrix + plan (done), board, rulings, gate run,
   freeze `stage-2/` at accepted revision.

Gate: verifier CONFIRMED **and** coordinator-run official harness
`--stage 2 --mode isolated` pass → `docs/gates/stage-2-freeze.md` → stage 3.

### 12b. Stage-3 run plan (completed)

Source spec: `D:\tk-official\tablekeeper\spec\stage-3.md` (inherits stages 1
and 2). Clause matrix: `docs/requirements-matrix-stage-3.md` (rulings
R3-1..R3-20). Contract deltas vs stage-2: `explain=true` availability
explanations, dated immutable policies and `manager_user_ids`, reservation
`revision`/`accepted_terms`, owner-only history and decision endpoints,
recurring `POST /series` + `GET /series/{id}`, stage-1/stage-2 export upgrade,
and policy-aware collective moves with series exception flags. The stage-3
spec explicitly requires no new screens; the inherited stage-2 UI remains the
browser surface.

1. **tk-engineer** — copy `stage-2/` → `stage-3/` verbatim (no pycache), then
   extend the API/domain: policy storage/selection/publication, explain output,
   reservation revisions/terms/history/decision, expected_revision, series,
   upgrade import, policy-aware moves, restaurant/series revision counters,
   Dockerfile/RUN.md.
2. **tk-experience** — `fixtures.py` `manager_user_ids` validation/default and
   demo seed manager coverage; stage-3 session/tests. No new screens are
   required; inherited UI must remain compatible.
3. **tk-verifier** — `verification/stage-3/` spec-derived matrix/checks
   (API, policy selection, history/terms, series, upgrade, concurrency,
   collective moves), then official harness `--stage 3` host + isolated and a
   CONFIRMED/HELD verdict. Never repairs product code.
4. **tk-coordinator** — matrix + plan (done), board, rulings, gate run,
   freeze `stage-3/` at accepted revision.

Gate: verifier CONFIRMED **and** coordinator-run official harness
`--stage 3 --mode isolated` pass → `docs/gates/stage-3-freeze.md` → stage 4.

### 12c. Stage-4 run plan (accepted; frozen)

Source spec: `D:\tk-official\tablekeeper\spec\stage-4.md` (inherits stages 1–3).
Clause matrix: `docs/requirements-matrix-stage-4.md` (rulings R4-1..R4-24).
Contract deltas vs stage-3: manager-only replan preview/apply, persistent
closures, deterministic optimal reassignment, `reassigned` history, stage-4
series clock-time amendments, closure-aware occupancy/explain, and stage-1–3
export upgrade. The stage-4 spec explicitly requires no new screens; the
inherited stage-2 UI remains the browser surface.

1. **tk-engineer** — copy `stage-3/` → `stage-4/` verbatim (no pycache), then
   extend the API/domain: replan preview, plan apply, closures, closure-aware
   occupancy/explain, series amend, upgrade import, Dockerfile/RUN.md.
2. **tk-experience** — preserve fixture/manager/demo-seed coherence and the
   inherited UI; add only a focused owned browser/closure regression check if
   practical. No new screens are required.
3. **tk-verifier** — `verification/stage-4/` spec-derived matrix/checks
   (replans, apply/stale/replay, closures, series amend, upgrade, concurrency,
   atomicity), then official harness `--stage 4` host + isolated and a
   CONFIRMED/HELD verdict. Never repairs product code.
4. **tk-coordinator** — matrix + plan (done), board, rulings, gate run,
   freeze `stage-4/` at accepted revision.

Gate: verifier CONFIRMED and coordinator-run official harness
`--stage 4 --mode isolated` passed; see `docs/gates/stage-4-freeze.md`.
Final `--all --mode isolated`, clean-clone validation, and room export remain
packaging gates.

Architecture the service grows into:

```arch
{
  "kind": "layered",
  "title": "Tablekeeper service architecture",
  "layers": [
    { "id": "client", "title": "Client layer", "items": [
      { "id": "browser_ui", "label": "Browser UI (stage 2+): search grid, booking, lookup, manager screens" },
      { "id": "http_clients", "label": "API clients / harness" } ] },
    { "id": "edge", "title": "HTTP edge (stdlib server)", "items": [
      { "id": "router", "label": "Router + JSON parse + error envelope" },
      { "id": "authn", "label": "Bearer auth + signup/login (scrypt)" },
      { "id": "idem", "label": "Idempotency registry (per-user keys, original responses)" },
      { "id": "testctl", "label": "/_test reset, export, import (hardened mode disables)" } ] },
    { "id": "domain", "title": "Domain core (one writer lock — linearizable)", "items": [
      { "id": "availability", "label": "Slot grid + table availability" },
      { "id": "reservations", "label": "Create / amend / cancel / moves" },
      { "id": "timeutil", "label": "IANA timezone, DST gap/overlap, absolute duration" },
      { "id": "policies", "label": "Stage 3: dated policies, accepted terms, reservation history" },
      { "id": "series", "label": "Stage 3: recurring series + occurrence exceptions" },
      { "id": "replanner", "label": "Stage 4: bounded optimal closure replans + atomic apply" } ] },
    { "id": "store", "title": "State", "items": [
      { "id": "state", "label": "In-memory state under single lock; optional WAL persistence" },
      { "id": "fixtures", "label": "Fixture parsing/validation + demo seed" } ] }
  ],
  "flows": [
    { "from": "client", "to": "edge", "label": "HTTP/JSON on PORT (default 8080)" },
    { "from": "router", "to": "authn", "label": "token check (except public/test routes)" },
    { "from": "router", "to": "idem", "label": "key resolve before field validation" },
    { "from": "edge", "to": "domain", "label": "check-and-act inside writer lock" },
    { "from": "domain", "to": "store", "label": "atomic mutate / snapshot for export" }
  ]
}
```

Key rulings live in `docs/requirements-matrix-stage-1.md` (and later-stage
siblings as they land).

## 13. Reference implementations studied

- `shi1720/WeAreDevelopers` — Tablekeeper, 4 seats, all stages accepted.
  Source of seat set, dispatch shape, module map.
- `yanerox69/dark-factory-pocketful` — Pocketful, refusal-gate pattern,
  coordinator mandate, measured FACTORY.md.
