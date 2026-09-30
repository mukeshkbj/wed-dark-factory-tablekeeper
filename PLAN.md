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

## 11. Reference implementations studied

- `shi1720/WeAreDevelopers` — Tablekeeper, 4 seats, all stages accepted.
  Source of seat set, dispatch shape, module map.
- `yanerox69/dark-factory-pocketful` — Pocketful, refusal-gate pattern,
  coordinator mandate, measured FACTORY.md.
