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
- A host that runs a **persistent Docker container** — Render, Railway,
  Fly.io, Cloud Run, a VPS, or similar. Serverless/edge platforms
  (Vercel, Netlify, Cloudflare Workers) do **not** fit: the service keeps
  its store in one process's memory, which ephemeral function instances
  cannot preserve, and adapting it would mean reopening the frozen product.
- Docker with the compose plugin for the compose variant below; the
  all-in-one image needs only a container runtime.
- TLS termination in front of the proxy (host reverse proxy, Caddy, load
  balancer, or the platform's built-in TLS). The stack itself serves plain
  HTTP on its published port.

## Two deployment shapes

**A. Compose stack** (`docker-compose.yml`) — for hosts with Docker Compose
(a VPS, a home server). Three services: internal app, one-shot seed,
public nginx proxy.

**B. All-in-one image** (`single/Dockerfile`) — for single-container hosts
(Render, Railway, Fly.io, Cloud Run, a droplet). One image carries app +
nginx + seed; only the nginx port is public.

```sh
# from the repository root
docker build -f submission/deploy/single/Dockerfile -t tablekeeper-demo .
docker run -d -p <public-port>:80 tablekeeper-demo      # or -e PORT=xxxx
```

Inside the container the app listens on `127.0.0.1:18080` (never publish
it); nginx listens on `$PORT` or 80 and blocks `/_test*`. Platforms that
inject a port (e.g. Cloud Run) work automatically.

**C. Render free tier (recommended)** — the repo includes `render.yaml`:
Dashboard → New → Blueprint → select this repository. Free plan = exactly
one instance (required for in-memory state), auto TLS on
`*.onrender.com`, no card needed. Caveats: spins down after ~15 min idle
(~1 min cold start — the seed reruns every cold start, so the demo
self-heals to the pristine fixture), and judge-created bookings vanish on
spin-down. A paid plan removes both if desired.

## Launch (compose variant)

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
