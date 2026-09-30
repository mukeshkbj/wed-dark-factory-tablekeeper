# Dark Factory — Tablekeeper

**Team:** `<team-name>` · **Track:** `tablekeeper` · WeAreDevelopers × BAND — Dark Factory (hackathon edition)

A software factory built in Band Desktop — four coding-agent seats that plan
work, implement it, hand off evidence, and check their own results — and the
clean-room reservation service that factory builds.

## How to read this repository

| Path | What it is |
|---|---|
| [`PLAN.md`](PLAN.md) | Project plan: schedule, seats, risks, definition of done |
| [`dispatch.md`](dispatch.md) | The single human task that ran the whole factory |
| [`mandates/`](mandates/) | One standing instruction (role file) per seat |
| `plan.md`, `architecture.json` | The room plan produced by the coordinator seat |
| `stage-1/` … `stage-4/` | One complete, buildable service per stage |
| `docs/` | Coverage matrices, `DEMO-RUNBOOK.md` |
| `evidence/` | Harness reports per stage (public-safe) |
| `FACTORY.md` | The factory story: seats, decisions, measurements, what it caught and missed |
| `room.json` | The Band room log, exported after the run — the evidence the code came from the band |

## Quick start

Each stage folder carries its own `RUN.md` — one command builds and runs it:

```sh
cd stage-1 && docker build -t tablekeeper-s1 . && docker run -p 8080:8080 tablekeeper-s1
```

(To be finalized once the official spec pins the port and env contract.)
