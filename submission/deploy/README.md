# Safe public demo deployment — Tablekeeper stage-4

## Why this stack exists

The frozen product (`stage-4/`) has two modes:

- **Judge/test mode (default):** `/_test/reset`, `/_test/export`, and
  `/_test/import` are live. Required to load the synthetic demo fixture, but
  **unsafe to expose publicly** — anyone could wipe or read the state.
- **Hardened mode (`TK_HARDENED=1`):** every `/_test/*` route returns `404`,
  but the in-memory state then starts empty — a bare hardened container shows
  judges an app with no restaurants and no way to create any.

This stack gets both properties without changing the product:

```
            ┌──────────── docker internal network (internal: true) ───────────┐
 public →   │  proxy (nginx, only published port)  ──►  app (default mode)    │
            │    blocks /_test* → 404                     ▲                   │
            │                                             │ one-shot          │
            │                                       seed (/_test/reset)       │
            └─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- A host and domain you are **authorized** to deploy to. This recipe does not
  pick a host for you.
- Docker with the compose plugin on that host.
- TLS termination in front of the proxy (host reverse proxy, Caddy, load
  balancer). The stack itself serves plain HTTP on its published port.

## Launch

```sh
cd submission/deploy
docker compose up --build -d
docker compose logs seed      # expect: "seeded synthetic demo fixture ..."
```

The app is then reachable on the proxy's published port (`8080` by default;
set `DEMO_PORT=<port>` to re-map without editing the file). If the chosen
host port is already taken, the container starts without a working forward —
pick a free port and confirm `docker compose ps` shows the mapping.

## Verify as an unauthenticated judge — required before claiming a URL

```sh
BASE=http://<host>:8080

curl -i $BASE/health                       # 200 {"status":"ok"}
curl -i $BASE/                             # 200 booking UI
curl -i -X POST $BASE/_test/reset          # 404 — test controls blocked
curl -i  $BASE/_test/export                # 404 — state dump blocked
curl -i -X POST $BASE/_test/import         # 404
curl -i -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@tablekeeper.test","password":"demo-pass-123"}'
                                           # 200 + token → seed data is live
```

Then walk the UI as a judge: sign up, search availability, book, look up a
reservation; log in as `ines@tablekeeper.test` / `ines-pass-789` (the seeded
manager of Zum Anker) to preview and apply a closure replan. All seeded
credentials are synthetic (`.test` domain) and safe to publish.

## Operational notes

- **State is in-memory.** Restarting `app` wipes all bookings, including any
  a judge created. Re-seed with `docker compose up --force-recreate seed`.
- **Single instance only.** The store is process-local; do not scale `app`.
- **No product code changed.** The stack wraps the frozen `stage-4/` image;
  verification evidence for that tree still applies.
- **Do not publish `app`'s port directly** — that would expose `/_test/*`.
- Hardened mode remains the correct choice for any deployment that does not
  need seeded demo data:

  ```sh
  docker run --rm -e TK_HARDENED=1 -p 8080:8080 tablekeeper-s4
  ```
