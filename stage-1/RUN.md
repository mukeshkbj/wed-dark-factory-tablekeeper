# Stage 1 — run the service

A single-container HTTP service. Everything it needs at runtime is inside the
image; no outbound network is used at run time.

## Build and run (Docker)

```sh
docker build -t tablekeeper-s1 .
docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-s1
```

Then:

```sh
curl http://localhost:8080/health    # -> {"status": "ok"}
```

The image listens on `0.0.0.0:$PORT` (default `8080`) and is ready within the
60-second startup budget.

## Local development (no Docker)

Python 3.12+ with the `tzdata` package (needed on Windows; Linux/macOS system
zone databases work as-is):

```sh
pip install tzdata
python src/server.py            # serves on PORT or 8080
python tests/local_checks.py    # spec-derived checks; BASE_URL=... to retarget
```

## Hardened deployment mode (optional)

By default the image enables the spec's test controls — `POST /_test/reset`,
`GET /_test/export`, `POST /_test/import` — unauthenticated, exactly as the
judge image requires. For any publicly exposed deployment, set:

```sh
docker run --rm -e PORT=8080 -e TK_HARDENED=1 -p 8080:8080 tablekeeper-s1
```

`TK_HARDENED=1` disables every `/_test/*` route (they answer `404 not_found`)
so fixtures, state export and import cannot be reached. Do not run the judge
image in hardened mode — the harness needs the test endpoints.

## State

State is in-process and ephemeral: a container restart loses it. Reset, export
and import round-trip all state (accounts, hashed passwords, live tokens,
reservations, idempotency receipts) as specified.
