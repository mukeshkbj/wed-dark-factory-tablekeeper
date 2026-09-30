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
| **Sep 30 (today)** | Spec kit path from user → read participant-guide + 4 specs → requirements matrix v0 → mandates + dispatch skeleton → repo scaffold → create 4 agents in Band (Role=mandate file, Runtime=Codex, workdir=this repo) → room `dark-factory-tablekeeper` + attach plan |
| **Oct 1 AM** | **Rehearsal:** dispatch stage-1 only. Verify @routing, task board, git identities, harness executes, token cost via `band usage`. Patch mandates. |
| **Oct 1 PM – Oct 3** | **Full run:** single dispatch, stages 1→4. Per stage: matrix → impl → UI (s2+) → verifier gate (own checks + harness N + inherited + `--mode isolated`) → freeze → copy folder forward. |
| **Oct 3–4** | Final `harness run --all --mode isolated` + clean-clone verify → export `room.json` → FACTORY.md with measurements → README/LICENSE/DEMO-RUNBOOK → optional hardened public demo + 3-min video + PDF |
| **Oct 4–5** | Submit on lablab. Oct 5 reserved as buffer for one re-run or fixes. |

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

## 8. Open decisions

1. **Stack** — recommendation: Python 3.12 + SQLite WAL + vendored deps (`zoneinfo`
   for DST). Alternative: Go single binary. Decide at kickoff after reading spec §2.
2. **Public demo** — optional hardened deployment (no `/_test`) vs. video-only demo.
3. **Team name / app title / credit name** for lablab + FACTORY.md.
4. **Band handle prefix** for seat naming (`@you/tk-*`).

## 9. Reference implementations studied

- `shi1720/WeAreDevelopers` — Tablekeeper, 4 seats, all stages accepted
  (120/145/152/158 checks). Source of seat set, dispatch shape, module map.
- `yanerox69/dark-factory-pocketful` — Pocketful, refusal-gate pattern,
  coordinator mandate, measured FACTORY.md.
