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

1. **Stack — RESOLVED (coordinator, scored run).** Python 3.12 stdlib-only:
   `http.server` threading + `sqlite3` single connection serialized by one
   re-entrant lock (linearizable by construction), `hashlib.scrypt` passwords,
   `zoneinfo` IANA/DST, `secrets` references. Image `python:3.12-slim`,
   `tzdata` vendored at build if needed. UI (stage 2+) server-rendered HTML +
   vanilla JS, assets inline — no CDN, no runtime network.
2. **Public demo** — hardened deployment vs video-only. `/_test` enabled in
   judge image; hardened mode flag disables all test endpoints for any exposed
   demo.
3. **Model reporting** — `swe` requested; seats record actual resolved id on
   first commit under `docs/seats/`. Coordinator reports `SWE-2 High`.

## 12. Scored run — live status

| Stage | Folder | State |
|---|---|---|
| 1 | `stage-1/` | gate R1 **REJECTED** at `695a903`: keep-alive request-body replay assigned as board `#5`; seed-reference ruling reversed (R16 / whole-run R12) after official-suite evidence; repair + verifier recheck in flight |
| 2 | `stage-2/` | pending stage-1 acceptance |
| 3 | `stage-3/` | pending |
| 4 | `stage-4/` | pending |

Coordinator artifacts: `docs/requirements-matrix-stage-1.md` (clause matrix +
rulings), `docs/seats/` (per-seat model records), `architecture.json` (room
diagram snapshot source).

## 13. Run architecture (room plan)

Extensible architecture chosen after reading all four specs — stack resolved:
Python 3.12 stdlib only (`ThreadingHTTPServer`, `sqlite3`, `hashlib.scrypt`,
`zoneinfo`, `secrets`), image `python:3.12-slim` + build-time `tzdata`. Work
split for stage 1 per the dispatched handoffs (`handoffs/`): **engineer** owns
`stage-1/Dockerfile` and `stage-1/src/`{errors,server,state,timeutil,
availability,reservations,moves,idempotency,transfer}`.py`;
**experience** owns `stage-1/src/auth.py`, `stage-1/src/fixtures.py`,
`stage-1/tests/` and `stage-1/RUN.md`; **verifier** derives its own check suite
from the spec text alone. Clause contract: `docs/requirements-matrix.md`
(whole-run) + `docs/requirements-matrix-stage-1.md` (dispatch numbering).

```arch
{
  "kind": "layered",
  "title": "Tablekeeper service architecture (all four stages)",
  "layers": [
    {
      "id": "clients",
      "title": "Clients",
      "items": [
        { "id": "browser_ui", "label": "Browser UI (search grid, booking, lookup, manager screens)", "detail": "Stage 2+: warm hospitality UI, testid contract, uncertain/refused recovery" },
        { "id": "api_consumers", "label": "API consumers & harness", "detail": "Official harness speaks HTTP only" }
      ]
    },
    {
      "id": "edge",
      "title": "HTTP edge",
      "items": [
        { "id": "server", "label": "Server, routing & error envelope", "detail": "stdlib ThreadingHTTPServer; exact status/code precedence; TK_HARDENED flag" },
        { "id": "authn", "label": "Signup / login / bearer auth", "detail": "scrypt password hashing, non-expiring tokens, multi-session" },
        { "id": "test_controls", "label": "/_test reset/export/import", "detail": "Unauthenticated; fixture apply + atomic state transfer" }
      ]
    },
    {
      "id": "domain",
      "title": "Domain core",
      "items": [
        { "id": "availability", "label": "Slot grid & availability", "detail": "IANA TZ/DST, explain rules (s3), declared pairs (s2)" },
        { "id": "booking", "label": "Reservations", "detail": "create/amend/cancel, cutoffs, occupancy" },
        { "id": "moves", "label": "Atomic reservation-moves", "detail": "all-or-nothing multi-booking batches" },
        { "id": "idempotency", "label": "Idempotency ledger", "detail": "per-user keys, byte-exact replay receipts" },
        { "id": "policies", "label": "Dated policies & terms", "detail": "s3: versioned selection, accepted_terms, revisions" },
        { "id": "series", "label": "Recurring series", "detail": "s3/4: occurrence generation, exceptions, series amend" },
        { "id": "replans", "label": "Closure replanning", "detail": "s4: bounded deterministic global optimizer + apply" },
        { "id": "history", "label": "History & revisions", "detail": "s3+: seq-ordered events, terms snapshots" }
      ]
    },
    {
      "id": "state",
      "title": "State",
      "items": [
        { "id": "store", "label": "Transactional state store", "detail": "one sqlite conn + one RLock; check-and-act is one critical section" },
        { "id": "export_import", "label": "Export / import snapshots", "detail": "atomic opaque state incl. credentials, tokens, receipts" }
      ]
    },
    {
      "id": "platform",
      "title": "Packaging & evidence",
      "items": [
        { "id": "docker_image", "label": "Single Docker image", "detail": "python:3.12-slim + tzdata; ≤2 vCPU / 2 GiB, PORT env, no runtime egress" },
        { "id": "docs", "label": "RUN.md / DEMO-RUNBOOK.md", "detail": "reproducible build + 3-minute demo" }
      ]
    }
  ],
  "flows": [
    { "from": "browser_ui", "to": "server", "label": "HTTP/JSON + pages" },
    { "from": "api_consumers", "to": "server", "label": "HTTP/JSON" },
    { "from": "server", "to": "authn", "label": "bearer check" },
    { "from": "server", "to": "idempotency", "label": "key claim before op" },
    { "from": "server", "to": "booking", "label": "validated commands" },
    { "from": "server", "to": "availability", "label": "queries" },
    { "from": "server", "to": "moves", "label": "batches" },
    { "from": "server", "to": "policies", "label": "manager writes" },
    { "from": "server", "to": "series", "label": "adopt / amend" },
    { "from": "server", "to": "replans", "label": "preview / apply" },
    { "from": "test_controls", "to": "store", "label": "reset / snapshot" },
    { "from": "test_controls", "to": "export_import", "label": "export / import" },
    { "from": "booking", "to": "idempotency", "label": "receipts" },
    { "from": "booking", "to": "store", "label": "atomic writes" },
    { "from": "moves", "to": "store", "label": "atomic writes" },
    { "from": "series", "to": "store", "label": "atomic writes" },
    { "from": "replans", "to": "store", "label": "atomic writes" },
    { "from": "policies", "to": "history", "label": "terms snapshots" },
    { "from": "booking", "to": "history", "label": "events" }
  ]
}
```

### Stage-1 seam (fixed by coordinator, dispatched verbatim to both seats)

- `errors.py` (engineer): `ApiError(status, code, message)`; edge raises, never
  tuples.
- `state.py` (engineer): `insert_user`, `user_by_email`, `user_by_id`,
  `insert_token`, `user_for_token`, `reset(fixture)` — one sqlite conn + one
  RLock; every check-and-act inside the lock.
- `auth.py` (experience): `handle_signup`, `handle_login`, `authenticate`,
  `hash_password`/`verify_password` (scrypt, self-contained stored form).
- `fixtures.py` (experience): `parse_fixture(body)`, `handle_reset(state,body)`;
  seeded users get hashed passwords; seeded reservations keep
  id/reference/user_id verbatim.
- `server.py` (engineer) wires routes to all of the above; `TK_HARDENED=1`
  turns every `/_test/*` into 404 (judge image runs without it).

## 14. Reference implementations studied

- `shi1720/WeAreDevelopers` — Tablekeeper, 4 seats, all stages accepted.
  Source of seat set, dispatch shape, module map.
- `yanerox69/dark-factory-pocketful` — Pocketful, refusal-gate pattern,
  coordinator mandate, measured FACTORY.md.
