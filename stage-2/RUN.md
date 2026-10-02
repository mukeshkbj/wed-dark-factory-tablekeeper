# Tablekeeper stage-1 — build and run

One command builds and starts the service (from this `stage-1/` directory):

```sh
docker build -t tablekeeper-s1 . && docker run --rm -p 8080:8080 tablekeeper-s1
```

Custom port (the service listens on `0.0.0.0:$PORT`, default `8080`):

```sh
docker build -t tablekeeper-s1 . && docker run --rm -e PORT=8123 -p 8123:8123 tablekeeper-s1
```

Check readiness: `GET /health` returns `{"status": "ok"}`.

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
HTTP contract end to end (auth, availability, reservations, idempotency,
DST, moves, export/import, concurrency).
