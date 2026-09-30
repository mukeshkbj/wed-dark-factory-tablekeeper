"""HTTP entry point and request pipeline.

Request order of business (matrix R1):

  1. Body parses as JSON and is an object where required -> 400 malformed
  2. Bearer token resolves, where required               -> 401 unauthenticated
  3. Idempotency-Key present where required              -> 400 / 422
  4. Ledger: replay -> 200 original; different body -> 409 key reuse
  5. Field validation -> 400 wrong type / 422 format & range
  6. Existence and ownership -> 404
  7. Domain rules -> endpoint-specific codes, conflicts last

Environment:
  PORT         listen port (default 8080)
  TK_HARDENED  when truthy, all /_test/* endpoints answer 404 (public deploys)

Owned by the engineer seat.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from .errors import ApiError
    from . import auth, fixtures, availability, reservations, moves, transfer
    from .state import State
except ImportError:
    from errors import ApiError
    import auth, fixtures, availability, reservations, moves, transfer
    from state import State

_MAX_BODY = 16 * 1024 * 1024

_PUBLIC_GETS = {"/restaurants", "/availability"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # Up to 50 requests in flight (spec section 2): the default listen
    # backlog of 5 would silently drop concurrent connections.
    request_queue_size = 128


def _truthy(value) -> bool:
    return bool(value) and str(value).lower() not in ("0", "false", "no")


class Handler(BaseHTTPRequestHandler):
    server_version = "Tablekeeper/1.0"
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # keep stdout clean; errors go to stderr
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, obj):
        try:
            if obj is None or status == 204:
                payload = b""
            else:
                payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            if payload:
                self.send_header("Content-Type",
                                 "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload and self.command != "HEAD":
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, err: ApiError):
        self._send(err.status, err.body())

    def _read_body(self):
        if hasattr(self, "_body"):
            return self._body
        length = self.headers.get("Content-Length")
        try:
            n = int(length) if length else 0
        except ValueError:
            n = 0
        if n > _MAX_BODY:
            raise ApiError(400, "malformed_request", "body too large")
        self._body = self.rfile.read(n) if n else b""
        return self._body

    def _json_object(self):
        """Body that must parse to a JSON object -> else 400 (R1a)."""
        raw = self._read_body()
        if not raw.strip():
            raise ApiError(400, "malformed_request", "body must be JSON")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "malformed_request", "body must be JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "malformed_request", "body must be an object")
        return data

    def _authenticate(self):
        return auth.authenticate(
            self.server.state, self.headers.get("Authorization"))

    def _idempotency_key(self):
        key = self.headers.get("Idempotency-Key")
        if key is None or key == "":
            raise ApiError(400, "missing_idempotency_key",
                           "Idempotency-Key header is required")
        if len(key) > 255:
            raise ApiError(422, "validation_failed",
                           "Idempotency-Key exceeds 255 characters")
        return key

    # -- routing ------------------------------------------------------------
    def _dispatch(self):
        path, _, query = self.path.partition("?")
        path = urllib.parse.unquote(path)
        params = {k: v[0] for k, v in
                  urllib.parse.parse_qs(query, keep_blank_values=True).items()}
        method = self.command
        state = self.server.state

        # Test controls: enabled by default, fully removed in hardened mode.
        if path.startswith("/_test/"):
            if self.server.hardened:
                raise ApiError(404, "not_found", "no such route")
            if path == "/_test/reset" and method == "POST":
                fixtures.handle_reset(state, self._json_object())
                return self._send(204, None)
            if path == "/_test/export" and method == "GET":
                return self._send(*transfer.handle_export(state))
            if path == "/_test/import" and method == "POST":
                return self._send(*transfer.handle_import(
                    state, self._json_object()))
            raise ApiError(404, "not_found", "no such route")

        if path == "/health" and method == "GET":
            return self._send(200, {"status": "ok"})

        if path == "/auth/signup" and method == "POST":
            body = self._json_object()
            return self._send(201, auth.handle_signup(state, body))
        if path == "/auth/login" and method == "POST":
            body = self._json_object()
            return self._send(200, auth.handle_login(state, body))

        # Public read surface (spec 8): no token required.
        if method == "GET" and path in _PUBLIC_GETS:
            if path == "/restaurants":
                return self._send(200, {"restaurants": [
                    {"id": r["id"], "name": r["name"],
                     "timezone": r["timezone"]}
                    for r in state.all_restaurants()]})
            return self._send(*availability.handle(state, params))
        if method == "GET" and path.startswith("/restaurants/"):
            rid = path[len("/restaurants/"):]
            restaurant = state.get_restaurant(rid) if rid else None
            if restaurant is None:
                raise ApiError(404, "not_found", "no such restaurant")
            return self._send(200, restaurant)

        # Everything below needs a bearer token.
        if path == "/reservations":
            if method == "POST":
                body = self._json_object()
                user = self._authenticate()
                key = self._idempotency_key()
                return self._send(
                    *reservations.create(state, user, body, key))
            if method == "GET":
                user = self._authenticate()
                return self._send(*reservations.list_mine(state, user))

        if path == "/reservation-moves" and method == "POST":
            body = self._json_object()
            user = self._authenticate()
            key = self._idempotency_key()
            return self._send(*moves.handle(state, user, body, key))

        if path.startswith("/reservations/"):
            rest = path[len("/reservations/"):]
            reference, _, suffix = rest.partition("/")
            if suffix == "cancel" and method == "POST" and reference:
                self._read_body()  # drain; body is ignored
                user = self._authenticate()
                return self._send(*reservations.cancel(state, user, reference))
            if reference and not suffix:
                if method == "GET":
                    user = self._authenticate()
                    return self._send(
                        *reservations.get_one(state, user, reference))
                if method == "PATCH":
                    body = self._json_object()
                    user = self._authenticate()
                    return self._send(
                        *reservations.patch(state, user, reference, body))

        raise ApiError(404, "not_found", "no such route")

    def _handle(self):
        try:
            # Always drain the request body first so a keep-alive connection
            # stays aligned regardless of whether the route consumes it.
            self._read_body()
            self._dispatch()
        except ApiError as err:
            self._error(err)
        except Exception as exc:  # pragma: no cover - defensive; never expected
            import traceback
            traceback.print_exc()
            self._error(ApiError(500, "internal_error", str(exc)))

    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = Server(("0.0.0.0", port), Handler)
    server.state = State()
    server.hardened = _truthy(os.environ.get("TK_HARDENED"))
    sys.stderr.write(
        f"tablekeeper stage-1 listening on 0.0.0.0:{port}"
        f" (hardened={server.hardened})\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
