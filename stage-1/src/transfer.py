"""State export and import test controls (spec section 10).

`GET /_test/export` returns an opaque snapshot under
`{track: "tablekeeper", format_version: 1, state: ...}`. The snapshot is taken
inside the state lock, so it is an atomic, consistent point; later writes do
not mutate it.

`POST /_test/import` validates the whole object, then atomically replaces all
state. It must accept this service's own export unchanged — preserving
accounts with hashed passwords, live bearer tokens, reservations, references
and every stored idempotent request/response — and it must leave the
destination untouched when the payload is invalid.

Owned by the engineer seat.
"""
from __future__ import annotations

try:
    from .errors import ApiError
except ImportError:
    from errors import ApiError

TRACK = "tablekeeper"
FORMAT_VERSION = 1


def handle_export(state):
    """GET /_test/export -> 200 with the opaque state object."""
    return 200, {"track": TRACK, "format_version": FORMAT_VERSION,
                 "state": state.export_state()}


def handle_import(state, body):
    """POST /_test/import -> 204 after atomic replacement."""
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_request", "body must be a JSON object")
    if body.get("track") != TRACK or body.get("format_version") != FORMAT_VERSION:
        raise ApiError(422, "validation_failed",
                       "unsupported track or format_version")
    if "state" not in body:
        raise ApiError(422, "validation_failed", "missing field: state")
    state.import_state(body["state"])
    return 204, None
