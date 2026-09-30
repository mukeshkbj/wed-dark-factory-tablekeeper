# Dark Factory — Tablekeeper

**Team:** `mukeshkbj` · **Track:** `tablekeeper` · WeAreDevelopers × BAND — Dark Factory

This repository holds two things that belong together: a small software
factory built in BAND Desktop — four coding-agent seats in one room that plan,
build, and check each other's work — and the reservation service that factory
produced, built clean-room from the official specification.

## How to read this repository

| Path | What it is |
|---|---|
| [`PLAN.md`](PLAN.md) | The project plan: seats, schedule, risks, definition of done |
| [`dispatch.md`](dispatch.md) | The one human task that ran the whole factory |
| [`mandates/`](mandates/) | One standing instruction file per seat — deliberately generic |
| `plan.md`, `architecture.json` | The room plan written by the coordinator seat |
| `stage-1/` … `stage-4/` | One complete, buildable service per stage |
| `docs/` | Requirements coverage and `DEMO-RUNBOOK.md` |
| `evidence/` | Harness reports per stage (public-safe) |
| [`FACTORY.md`](FACTORY.md) | How the factory actually ran — seats, decisions, what review caught |
| `room.json` | The exported Band room — proof the seats did the work |

## Quick start

Every stage folder is self-contained: `Dockerfile`, `RUN.md`, source, tests.
One command builds and runs it — the service listens on `0.0.0.0:$PORT`
(default 8080) and needs no outbound network:

```sh
cd stage-4 && docker build -t tablekeeper . && docker run -e PORT=8080 -p 8080:8080 tablekeeper
```

`GET /health` answers once the container is ready. `RUN.md` in each folder is
the authoritative command.
