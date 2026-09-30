# Dark Factory — Tablekeeper: Project Plan

**Event:** WeAreDevelopers × BAND — Dark Factory (lablab.ai), Sept 26 – Oct 5, 2026
**Track:** `tablekeeper` · **Seat runtime:** Codex · **Submission repo:** `D:\WED Dark factory`

## 1. Mission

Build a **software factory** in Band Desktop: four Codex agent seats in one room
that turn the official Tablekeeper spec into a verified, independently-buildable
service across **4 stages** — then package the factory itself (mandates, room
log, measured evidence) as the submission.

Grading is automated and literal. ~91% of checks are hidden (stage 3 ships ~9%).
The differentiator is not speed — it is a factory that **refuses to hand off
non-conforming work**.

## 2. Deliverables (submission checklist)

| Artifact | Status |
|---|---|
| Public GitHub repo (this folder) | scaffold today |
| `mandates/` — 4 seat role files | drafting today |
| `dispatch.md` — one-shot run brief | skeleton today, fills after spec |
| `stage-1/` … `stage-4/` — each: Dockerfile, RUN.md, CONFORMANCE.md, src, tests | from the run |
| `plan.md` + `architecture.json` — room plan | coordinator seat |
| `docs/` — coverage matrix per stage, DEMO-RUNBOOK.md | during run |
| `evidence/` — harness reports (public-safe) | during run |
| `FACTORY.md` — seats, decisions, measured time/tokens/cost, caught vs missed | final |
| `room.json` — real Band export (post-run, never fabricated) | final |
| `README.md` + `LICENSE` (MIT) | final |
| lablab fields: title, description, tech tags, presentation PDF, demo link | Oct 4 |

## 3. Seats

| Seat | Mandate | Owns | Forbidden |
|---|---|---|---|
| `tk-coordinator` | `mandates/tk-coordinator.md` | requirements matrix, plan/architecture, task board, acceptance, FACTORY.md | product code |
| `tk-engineer` | `mandates/tk-engineer.md` | domain impl: state, reservations, availability, series, policies, replans, temporal, auth, portability, Dockerfile | UI |
| `tk-experience` | `mandates/tk-experience.md` | stage-1 impl share, UI (s2+), manager screens, seed data, DEMO-RUNBOOK | domain core |
| `tk-verifier` | `mandates/tk-verifier.md` | spec-derived coverage matrix, own checks, official harness runs, gate verdicts | product code |

All four run the same harness + model — differentiation is the mandate, not the model.

## 4. Day-by-day schedule

| Day | Workstream |
|---|---|
| **Sep 30 (today)** | ✅ Kit cloned `D:\tk-official` @ `803560d` · ✅ harness venv + chromium installed · ✅ mandates + dispatch + scaffold committed → **User: Band setup (below)** |
| **Oct 1 AM** | **Toy rehearsal** (`dispatch-toy.md`, repo `D:\band-work\toy-result`): proves @routing, board, git identities, harness, `harness check` gates 1+2, token cost. The toy is unscored — iterate freely here. |
| **Oct 1 PM – Oct 3** | **Scored run**: fresh room, seats' workdir = `D:\WED Dark factory`, paste `dispatch.md` once — the ONLY human input allowed. Stages 1→4 with verifier gate per stage. |
| **Oct 3–4** | Final `--all --mode isolated` + fresh-clone `harness check` → `room.json` export (Band console → Download full session) → fill FACTORY.md → video **with room recording** (required) + PDF |
| **Oct 4–5** | Submit repo URL + presentation + video on lablab. Oct 5 23:59 PDT hard close. |

## 5. Engineering requirements (Tablekeeper, from proven dispatch)

- Linearizable writes under 50 concurrent requests
- Exact idempotency scoping + original receipts
- Atomic batches with failure rollback
- IANA timezone/DST correctness, absolute durations
- Strict specified type/error precedence
- Password hashing, owner isolation
- Validated atomic imports preserving credentials/receipts/histories/opaque IDs
- Immutable historical terms; recurring identity/exceptions
- **Bounded deterministic globally-optimal closure planning** (stage-4 differentiator)
- Single image ≤ 2 vCPU / 2 GiB; no runtime outbound network; `/_test` endpoints
  enabled in judge image, disabled in documented hardened demo mode
- UI (stage 2+): real signup/login, booking search, responsive 375px+desktop,
  `data-testid` hooks, a11y, manager screens for policies/series/closure-preview-and-apply

## 6. Risk register

| Risk | Mitigation |
|---|---|
| Spec kit not located → nothing can start | **Blocker #1: user provides kit path today.** Everything else is ready. |
| Hidden tests ≠ visible samples | Verifier derives checks from spec text only; coverage matrix with gap flags |
| Ambiguous spec sentences | Coordinator records a ruling per ambiguity in the matrix; spec wins over taste |
| Seats don't wake (mention-routing) | Rehearsal proves routing; handoffs paste full task+spec, numbered + FINAL marker |
| Room history cost blowup (54:1 in:out observed) | Bounded handoffs; focused seats; monitor `band usage`; budget cap ~$25 |
| Daemon/seat crash mid-run | Restart same seats + room, new provider sessions, no new task/hints (proven recovery) |
| Later stage breaks earlier contract | Spec-grounded fix + reverify affected folders; never retrofit backward |
| Time overrun | Stage-1 rehearsal validates the pipeline early; Oct 5 is pure buffer |

## 7. Definition of Done — per stage

- [ ] Verifier's spec-derived matrix shows every clause covered or flagged
- [ ] Official harness: stage N checks + all inherited suites pass
- [ ] `--mode isolated` passes (no outbound network)
- [ ] Next-stage overshoot probe fails as expected (where applicable)
- [ ] Folder frozen at a named commit; Dockerfile builds clean; RUN.md accurate
- [ ] Original commits preserved (no squash/amend/rebase)

## 8. Hard rules (from the official participant guide — DQs)

- **Mandates must be generic** — no track vocabulary (endpoints, fields, error
  codes). Track detail lives only in the dispatched task. ✅ enforced in ours.
- **The scored run is hands-off**: the dispatch is the only human input; no
  steering, approvals, hints or reruns. Develop/rehearse freely BEFORE it —
  the submitted run happens in a fresh room.
- **Hand-built stage code doesn't count** — `stage-N/` commits must come from
  seats, traceable to the room log. Operator may commit mandates/README/docs.
- **room.json** = full session download from Band console (room ⋮ → Open in
  Band → ⋮ → Download full session), committed unchanged.
- **Video must show the Band room** (the room, a handoff, the result).
- **Mandate files named after the seat as the room shows it**; each must carry
  `Harness:` and `Model:` (exact id) lines — fill real model ids at agent
  creation.
- **Stage claiming**: stage-N passes ≥half of every suite 1..N AND must not
  pass all of suite N+1 (overshoot = misplaced answer, earns nothing).
- `harness check` runs gates 1+2+4 offline — run it before every push.
- Help: BAND Discord (discord.com/invite/5YkNXmYfjk) for Band/harness;
  lablab Discord for event/platform. Spec ambiguities → ask, answered publicly.

## 9. Environment status

| Need | State |
|---|---|
| Kit `D:\tk-official` @ 803560d | ✅ cloned, pristine |
| Harness venv `D:\tk-official\.venv` | ✅ `python -m harness` works |
| Playwright chromium | ✅ installed |
| Docker daemon | ⚠️ **Docker Desktop not running — start it before harness runs** |
| Codex CLI 0.44.0 | ✅ installed, ChatGPT login |
| Band account | ✅ @mukeshkbj signed in, no agents yet |
| WSL2 | ✅ available if needed (guide suggests it on Windows; native venv already works) |

## 10. Open decisions

1. **Stack** — recommendation: Python 3.12 + SQLite WAL + vendored deps
   (`zoneinfo` covers the IANA/DST contract). Go single binary is the
   alternative. Coordinator seat decides after reading spec §2.
2. **Public demo** — optional hardened deployment vs. video-only.
3. **Team name / app title** for lablab + README.
4. **Model id** — fill each mandate's `Model:` line with the exact id Band
   shows when creating the seats (same for all four).

## 11. Reference implementations studied

- `shi1720/WeAreDevelopers` — Tablekeeper, 4 seats, all stages accepted
  (120/145/152/158 checks). Source of seat set, dispatch shape, module map.
- `yanerox69/dark-factory-pocketful` — Pocketful, refusal-gate pattern,
  coordinator mandate, measured FACTORY.md.
