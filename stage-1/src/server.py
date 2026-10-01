"""Tablekeeper stage-1 HTTP service.

Python 3.12+ stdlib only. ThreadingHTTPServer on 0.0.0.0:$PORT (default 8080).
All request handling that touches shared state runs under one re-entrant
lock (state.LOCK), so every check-and-act is one linearizable critical
section. Every 4xx body is {"error": {"code", "message"}}; nothing here
may produce a 5xx.
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import state
from errors import ApiError, err_body

try:
    import fixtures
except ImportError:  # experience-owned module may not have landed yet
    import _stub_fixtures as fixtures

import auth
import availability
import moves
import reservations
import transfer

_JSON_CT = "application/json; charset=utf-8"
_MAX_BODY = 16 * 1024 * 1024


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Tablekeeper/1.0"

    # ---- plumbing ----------------------------------------------------

    def log_message(self, fmt, *args):  # keep stderr quiet
        pass

    def _read_body(self):
        length = self.headers.get("Content-Length")
        if length is None:
            return b""
        try:
            n = int(length)
        except ValueError:
            raise ApiError(400, "malformed_request", "bad Content-Length")
        if n < 0 or n > _MAX_BODY:
            raise ApiError(400, "malformed_request", "bad Content-Length")
        return self.rfile.read(n) if n else b""

    def _send(self, status, obj):
        if obj is None:
            payload = b""
        else:
            payload = _json_bytes(obj)
        self.send_response(status)
        self.send_header("Content-Type", _JSON_CT)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload and self.command != "HEAD":
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler would emit HTML (and 5xx for bad method /
        # version). Emit our JSON shape and never a 5xx.
        status = code if 400 <= code < 500 else 400
        known = {
            400: "malformed_request", 401: "unauthenticated",
            403: "forbidden", 404: "not_found", 405: "not_found",
        }
        self._send(status, {"error": {
            "code": known.get(status, "malformed_request"),
            "message": message or "request error",
        }})

    # ---- dispatch ----------------------------------------------------

    def _handle(self):
        try:
            status, obj = self._route()
        except ApiError as exc:
            status, obj = exc.status, err_body(exc)
        except fixtures.FixtureError as exc:
            status, obj = exc.status, {"error": {
                "code": exc.code, "message": str(exc)}}
        except Exception:
            status, obj = 400, {"error": {
                "code": "internal_error", "message": "internal error"}}
        try:
            self._send(status, obj)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = lambda self: self._handle()
    do_POST = lambda self: self._handle()
    do_PUT = lambda self: self._handle()
    do_PATCH = lambda self: self._handle()
    do_DELETE = lambda self: self._handle()
    do_HEAD = lambda self: self._handle()
    do_OPTIONS = lambda self: self._handle()
    do_TRACE = lambda self: self._handle()

    def _route(self):
        split = urlsplit(self.path)
        path = split.path
        method = "GET" if self.command == "HEAD" else self.command
        query = parse_qs(split.query, keep_blank_values=True)
        query = {k: v[0] for k, v in query.items()}

        # Body read happens before the lock; only parsed for handlers that
        # want it. Non-object JSON is rejected inside _json_object.
        raw = self._read_body()

        with state.LOCK:
            if method == "GET" and path == "/health":
                return 200, {"status": "ok"}

            if method == "POST" and path == "/_test/reset":
                return transfer.reset(raw)
            if method == "GET" and path == "/_test/export":
                return transfer.export()
            if method == "POST" and path == "/_test/import":
                return transfer.do_import(raw)

            if method == "POST" and path == "/auth/signup":
                return auth.signup(self._json_object(raw))
            if method == "POST" and path == "/auth/login":
                return auth.login(self._json_object(raw))

            if method == "GET" and path == "/restaurants":
                return 200, availability.list_restaurants()
            m = re.fullmatch(r"/restaurants/([^/]+)", path)
            if method == "GET" and m:
                return 200, availability.get_restaurant(unquote(m.group(1)))
            if method == "GET" and path == "/availability":
                return 200, availability.search(query)

            if path == "/reservations" and method == "POST":
                user = auth.require_user(self.headers)
                key = self._idem_key()
                body = self._json_object(raw)
                return reservations.create_idempotent(
                    user, method, path, key, body)
            if path == "/reservations" and method == "GET":
                user = auth.require_user(self.headers)
                return reservations.list_mine(user)

            m = re.fullmatch(r"/reservations/([^/]+)/cancel", path)
            if m and method == "POST":
                user = auth.require_user(self.headers)
                return reservations.cancel(user, unquote(m.group(1)))

            m = re.fullmatch(r"/reservations/([^/]+)", path)
            if m:
                ref = unquote(m.group(1))
                if method == "GET":
                    user = auth.require_user(self.headers)
                    return reservations.get_one(user, ref)
                if method == "PATCH":
                    user = auth.require_user(self.headers)
                    body = self._json_object(raw)
                    return reservations.patch(user, ref, body)

            if path == "/reservation-moves" and method == "POST":
                user = auth.require_user(self.headers)
                key = self._idem_key()
                body = self._json_object(raw)
                return moves.apply_idempotent(user, method, path, key, body)

            raise ApiError(404, "not_found", "no such route")

    # ---- helpers -----------------------------------------------------

    def _json_object(self, raw):
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "malformed_request", "body is not JSON")
        if not isinstance(obj, dict):
            raise ApiError(400, "malformed_request",
                           "body must be a JSON object")
        return obj

    def _idem_key(self):
        key = self.headers.get("Idempotency-Key")
        if key is None or key == "":
            raise ApiError(400, "missing_idempotency_key",
                           "Idempotency-Key header required")
        if len(key) > 255:
            raise ApiError(422, "validation_failed",
                           "Idempotency-Key must be 1..255 chars")
        return key


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
