# Tablekeeper stage-4 — build and run

One command builds and starts the service (from this `stage-4/` directory):

```sh
docker build -t tablekeeper-s4 . && docker run --rm -p 8080:8080 tablekeeper-s4
```

Custom port (the service listens on `0.0.0.0:$PORT`, default `8080`):

```sh
docker build -t tablekeeper-s4 . && docker run --rm -e PORT=8123 -p 8123:8123 tablekeeper-s4
```

Check readiness: `GET /health` returns `{"status": "ok"}`.

The browser UI is served from `ui/` when that directory is present in the
image: `/`, `/signup`, `/login`, `/lookup`, and `/static/*`. API behaviour is
unchanged by the UI routes.

Stage 4 keeps every stage-1 through stage-3 endpoint and adds manager-only
closure replanning plus owner-only recurring-series time amendments:

- `POST /restaurants/{id}/replans` previews a deterministic repair plan for an
  absolute half-open table-closure interval.
- `POST /restaurants/{id}/replans/{plan_id}/apply` atomically records the
  closure and moves the selected bookings; moved bookings gain a `reassigned`
  history entry and keep their times, owners, party sizes, and accepted terms.
- Applied closures block overlapping singles and declared pairs in
  availability, explanations, creates, amendments, moves, series adoption,
  series amendments, and later replans.
- `POST /series/{id}/amend` changes the clock time for eligible occurrences at
  or after `from_index`, preserving each occurrence's date, table selection,
  party size, and identity. Cancelled and exception occurrences are skipped.

Imported stage-1/2/3 exports are upgraded to empty `plans`/`closures` state;
stage-4 exports preserve pending/applied plans, applied closures, histories,
terms, revisions, series, counters, and idempotency records. Imported
reservations without stage-3 metadata are still normalised to policy 0,
revision 1, and a reconstructed `created` history entry.

## Hardened mode

Judge/test mode is the default: `/_test/reset`, `/_test/export`, and
`/_test/import` are enabled. For a public demo deployment, set
`TK_HARDENED=1` to make every `/_test/*` route return `404`:

```sh
docker run --rm -e TK_HARDENED=1 -p 8080:8080 tablekeeper-s4
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

The suite starts the real server on an ephemeral port and exercises the HTTP
contract end to end (auth, availability, explanations, policies, reservation
terms/history/revisions, series creation and amendments, closure replans,
combined tables, idempotency, DST, moves, export/import, and concurrency).
