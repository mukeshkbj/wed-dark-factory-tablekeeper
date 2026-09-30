# FACTORY — dark factory `tablekeeper`

> Draft scaffold — filled after the scored run with measured numbers.

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

## Measured (filled post-run)

- Wall time per stage, token usage and cost per seat (`band usage`)
- What review caught: _TBD_
- What review missed: _TBD_
- Accepted revisions per stage: _TBD_
