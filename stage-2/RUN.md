# Tablekeeper stage-2 — build and run

One command builds and starts the service (from this `stage-2/` directory):

```sh
docker build -t tablekeeper-s2 . && docker run --rm -p 8080:8080 tablekeeper-s2
```

Custom port (the service listens on `0.0.0.0:$PORT`, default `8080`):

```sh
docker build -t tablekeeper-s2 . && docker run --rm -e PORT=8123 -p 8123:8123 tablekeeper-s2
```

Check readiness: `GET /health` returns `{"status": "ok"}`.

The browser UI is served from `ui/` when that directory is present in the
image: `/`, `/signup`, `/login`, `/lookup`, and `/static/*`. API behaviour is
unchanged by the UI routes.

## Hardened mode

Judge/test mode is the default: `/_test/reset`, `/_test/export`, and
`/_test/import` are enabled. For a public demo deployment, set
`TK_HARDENED=1` to make every `/_test/*` route return `404`:

```sh
docker run --rm -e TK_HARDENED=1 -p 8080:8080 tablekeeper-s2
```

## Local development (no Docker)

Python 3.12+ with a timezone database available (Debian `tzdata` package or
the PyPI `tzdata` wheel on platforms without a system tzdb):

```sh
python src/server.py          # PORT env var honored, default 8080
```

## Tests

```sh
python -m unittest discover -s tests -v
```

The suite starts the real server on an ephemeral port and exercises the
HTTP contract end to end (auth, availability, combined-table reservations,
idempotency, DST, moves, export/import, concurrency).
