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

## Measured (filled post-run)

- Wall time per stage, token usage and cost per seat (`band usage`)
- What review caught: _TBD_
- What review missed: _TBD_
- Accepted revisions per stage: _TBD_
