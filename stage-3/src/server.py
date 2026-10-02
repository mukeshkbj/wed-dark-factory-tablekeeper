"""Tablekeeper stage-2 HTTP service.

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
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
_UI_DIR = os.path.join(_ROOT_DIR, "ui")
_STATIC_DIR = os.path.join(_UI_DIR, "static")
_UI_ROUTES = {
    "/": "index.html",
    "/signup": "signup.html",
    "/login": "login.html",
    "/lookup": "lookup.html",
}
_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class _TeeReader:
    """Pass-through reader that records bytes consumed (headers only —
    the wrapped stream is restored before the request body is read)."""

    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.buf = bytearray()

    def readline(self, *args):
        line = self.wrapped.readline(*args)
        self.buf += line
        return line

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


class _FileResponse:
    def __init__(self, body, content_type):
        self.body = body
        self.content_type = content_type


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _hardened():
    return os.environ.get("TK_HARDENED", "").lower() in (
        "1", "true", "yes", "on")


def _content_type(path):
    return _STATIC_TYPES.get(
        os.path.splitext(path)[1].lower(), "application/octet-stream")


def _file_response(path):
    try:
        if not os.path.isfile(path):
            raise OSError("missing")
        with open(path, "rb") as fh:
            body = fh.read()
    except OSError:
        raise ApiError(404, "not_found", "no such resource")
    return 200, _FileResponse(body, _content_type(path))


def _static_response(path):
    rel = unquote(path[len("/static/"):])
    candidate = os.path.abspath(os.path.join(_STATIC_DIR, rel))
    root = os.path.abspath(_STATIC_DIR)
    try:
        if os.path.commonpath((root, candidate)) != root:
            raise ApiError(404, "not_found", "no such resource")
    except ValueError:
        raise ApiError(404, "not_found", "no such resource")
    return _file_response(candidate)


def _ui_response(path):
    if path in _UI_ROUTES:
        return _file_response(os.path.join(_UI_DIR, _UI_ROUTES[path]))
    if path.startswith("/static/"):
        return _static_response(path)
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Tablekeeper/2.0"

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
        if isinstance(obj, _FileResponse):
            payload = obj.body
            content_type = obj.content_type
        elif obj is None:
            payload = b""
            content_type = _JSON_CT
        else:
            payload = _json_bytes(obj)
            content_type = _JSON_CT
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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

    def parse_request(self):
        # Capture the raw header block while the stdlib parses it: the email
        # parser strips trailing whitespace, which would erase a
        # whitespace-only Idempotency-Key (ruling G-10: such keys are valid).
        tee = _TeeReader(self.rfile)
        self.rfile = tee
        try:
            return super().parse_request()
        finally:
            self.rfile = tee.wrapped
            self._raw_headers = bytes(tee.buf)

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

        if method == "GET":
            ui = _ui_response(path)
            if ui is not None:
                return ui

        with state.LOCK:
            if method == "GET" and path == "/health":
                return 200, {"status": "ok"}

            if _hardened() and (path == "/_test" or
                                path.startswith("/_test/")):
                raise ApiError(404, "not_found", "no such route")
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
                # Order: JSON-object parse -> auth -> key -> idempotency
                # -> field validation (spec 5/7; verifier C-ERR-1).
                body = self._json_object(raw)
                user = auth.require_user(self.headers)
                key = self._idem_key()
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
                    body = self._json_object(raw)
                    user = auth.require_user(self.headers)
                    return reservations.patch(user, ref, body)

            if path == "/reservation-moves" and method == "POST":
                body = self._json_object(raw)
                user = auth.require_user(self.headers)
                key = self._idem_key()
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
        # Prefer the raw wire value: the email parser strips trailing
        # whitespace, so "Idempotency-Key:  " would otherwise read as
        # empty. Ruling G-10: whitespace-only keys are valid; never trim.
        key = None
        for line in getattr(self, "_raw_headers", b"").split(b"\n"):
            line = line.rstrip(b"\r")
            if line.lower().startswith(b"idempotency-key:"):
                raw = line.split(b":", 1)[1]
                if raw.startswith(b" "):
                    raw = raw[1:]
                key = raw.decode("latin-1")
                break
        if key is None:
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
