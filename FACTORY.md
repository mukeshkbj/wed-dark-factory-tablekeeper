# FACTORY — dark factory `tablekeeper`

> Seat recipe and rehearsal findings below are final. The scored-run numbers
> are filled after the run completes.

## Seats

| Seat | Harness | Model | Owns |
|---|---|---|---|
| `tk-coordinator` | Devin (ACP) | `swe` | spec → requirements matrix, plan, task board, gate, this file's inputs |
| `tk-engineer` | Devin (ACP) | `swe` | domain implementation, atomic state, Dockerfile |
| `tk-experience` | Devin (ACP) | `swe` | UI surface, manager screens, demo assets |
| `tk-verifier` | Devin (ACP, `--agent-type review`) | `swe` | spec-derived checks, official harness, acceptance verdicts |

## Design choices

- **Same runtime + model on every seat.** Differentiation comes from the
  mandate, not model quality — nothing is gained by giving one role a better
  brain, and it keeps the factory's claims clean.
- **Mandates are generic.** They describe how a seat works — what it owns, how
  it hands off, when it rejects. Track detail lives only in the dispatched
  task, where it belongs.
- **The verifier is independent and adversarial.** It builds its checks from
  the specification text, never from the shipped sample suite (which is a
  partial sample). Findings route back to the author; the verifier never
  repairs product code.
- **The gate is literal.** Acceptance requires the official harness: stage N
  plus all inherited suites, then `--mode isolated` (no outbound network,
  2 vCPU / 2 GiB) — the same conditions the judges run.

## Seat setup (reproducible)

Each seat is a Band-owned ACP agent running the Devin CLI:

```sh
# one-time, per machine: authenticate the standalone CLI (Band injects the
# API key into each spawned ACP session via `authenticate`)
"C:\Users\mukes\AppData\Local\devin\cli\bin\devin.exe" auth login

# per seat (unique --session scope per seat: setup-tk-<seat>)
band agent create --name tk-<seat> --transport acp \
  --spawn-command "C:\Users\mukes\AppData\Local\devin\cli\bin\devin.exe" \
  --spawn-arg=acp --spawn-arg=--model --spawn-arg=swe \
  --cwd "<result repo>" --session setup-tk-<seat>
band runtime template set --as @mukeshkbj/tk-<seat> \
  --runtime-auth api_key --runtime-env WINDSURF_API_KEY --runtime-env DEVIN_API_KEY
# verifier adds: --spawn-arg=--agent-type --spawn-arg=review
```

Notes proven in rehearsal (`D:\band-work\toy-result`):

- ACP seats cannot carry Band role files; the dispatch tells each seat to read
  `mandates/tk-<seat>.md` in the result repo before acting. The mandate file is
  both the seat's standing instruction and the submitted artifact.
- `--mode isolated` under native Windows passes backslash paths to pytest
  inside the Linux runner container (upstream defect). Run the harness under
  WSL2 (`python3 -m harness` from `/mnt/d/tk-official`) or substitute a
  `docker network --internal` equivalence run, which was done in rehearsal.
- `band chat add` may print a decode error while membership actually succeeds —
  verify with `chat participants`, never blindly retry `chat new`.

## Rehearsal findings (toy track, `D:\band-work\toy-result`)

Rehearsed on the unscored `toy` track before the scored run — same four seats,
same mandate mechanism, single dispatch. All four toy stages accepted in ~2h
wall time, `claimed stage: 4`, cumulative 24/24 shipped checks green. What it
proved and what it caught:

- **Proved**: mention-routed handoffs, board-driven task flow, per-seat git
  identities, frozen folders, copy-forward chain, verifier independence (it
  caught a real stage-2 render bug the shipped suite missed).
- **Caught — seat wake-loops**: keep-alive/acknowledgement messages wake seats
  and burned ~140k tokens of engineer context; a `true`-poll turn stalled
  stage-2 for ~25 min. Mandates now require: act only on work-carrying
  messages, end turns, never poll in-turn, no keep-alives.
- **Caught — self-healing**: coordinator diagnosed the stall, dispatched a
  status-check, restarted the runtime, and re-dispatched — recovery path works.
- **Caught — harness defect**: `--mode isolated` on Windows passes backslash
  paths into the Linux runner (upstream bug); WSL2 harness path verified clean.

## Scored run

### Frozen product revisions and gate outcomes

| Stage | Accepted product revision | Freeze/evidence | Official harness at that stage |
|---|---|---|---|
| 1 | `28b16f4` | freeze `aae0226` | 120/120 isolated |
| 2 | `5be5343` | freeze `e4087b6` | 25/25 isolated; initial rejection repaired before acceptance |
| 3 | `d9d04ba` | freeze `7e957fe` | 7/7 isolated; verifier also passed the host run |
| 4 | `579f39c` | freeze `db6a8dd` | 6/6 isolated; verifier also passed the host run |

The final official `--all --mode isolated` sweep at `db6a8dd` reports highest contiguous stage 4. Its stage-4 folder passes stages 1–4 (120/120, 25/25, 7/7, 6/6). A fresh shallow clone of public commit `d32b368` independently reproduces the same result. Earlier stage folders intentionally fail the next-stage overshoot probe while each still passes its own claimed stage. Reports are under `evidence/harness/final-all-isolated/` and `evidence/harness/final-all-clean-clone/`.

### What review caught

- Stage 1: email validation was too strict for the specified `local@domain` floor; fixture validation also rejected inputs allowed by the ruling. Both were repaired and re-verified.
- Stage 2: the hidden no-slots UI element could win an availability-grid selector and cause successful searches to time out. The verifier rejected the first candidate; the repair detached the inactive element from the DOM, then passed the official harness.
- Stage 3: the independent verifier suite and official host/isolated harness found no confirmed product defect.
- Stage 4: the independent verifier suite (862/862 combined API checks, 62/62 upgrade, 5/5 hardened, 82/82 inherited UI) and official host/isolated harness found no confirmed product defect. Several initial verifier failures were traced to verifier-side fixtures/check assumptions and corrected without changing the accepted product tree.

### Measurement and limitations

- Seat-level token usage and cost were not captured in a complete, attributable ledger: **unknown**. Do not infer these values from context-window telemetry.
- End-to-end wall time per stage was not recorded as a consistent dispatch-to-freeze metric: **unknown**. The stage-4 verifier's combined suite duration was recorded separately as 2337.5 seconds; it is test runtime, not total stage duration.
- No authoritative retrospective ground truth exists for findings missed by review: **unknown**. Passing the published harness and independent suites does not guarantee hidden judging tests.
- Recovery evidence includes an ACP authentication outage, two scored rooms reaching their message cap, the stage-2 verifier rejection/repair loop, and a false stage-3 route failure caused by stale local listeners. The stale-listener issue was resolved by using clean ports before final acceptance.
- `room.json` is not included yet. The operator must download the full real session from Band, inspect it for credentials, then run the official offline `harness check`; no room transcript is fabricated here.
