"""Authentication and password hashing (spec section 6).

Owned by the experience seat. Interface contract (fixed by coordinator):

    hash_password(pw) -> str
    verify_password(pw, stored) -> bool
    handle_signup(state, body) -> dict          # 201 body
    handle_login(state, body) -> dict           # 200 body
    authenticate(state, authorization_header) -> user dict

Errors are raised as ApiError from errors.py (engineer-owned).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

try:  # package layout (src is a package)
    from .errors import ApiError
except ImportError:  # flat layout (src on sys.path)
    from errors import ApiError

# scrypt parameters: n=2**14, r=8, p=1 needs ~16 MiB, comfortably inside the
# container budget. The parameter set is embedded in the stored string so
# verification stays self-contained and migrations can change defaults later.
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 128 * 1024 * 1024
_SALT_BYTES = 16
_SCHEME = "scrypt"

# local@domain: non-empty local part, exactly one '@', non-empty domain, no
# whitespace. The spec defines validity only as `local@domain`.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")

_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Hash `password` with scrypt; returns a self-contained `str`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN, maxmem=_SCRYPT_MAXMEM,
    )
    return "{}${}${}${}${}${}".format(
        _SCHEME, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        salt.hex(), digest.hex(),
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of `password` against a `hash_password` output."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != _SCHEME:
            return False
        n, r, p = int(n), int(r), int(p)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=n, r=r, p=p, dklen=len(expected), maxmem=_SCRYPT_MAXMEM,
    )
    return hmac.compare_digest(candidate, expected)


def _require_str(body: dict, field: str) -> str:
    """Missing -> 422; present but not a string -> 400 (spec section 5)."""
    if field not in body:
        raise ApiError(422, "validation_failed", f"missing field: {field}")
    value = body[field]
    if not isinstance(value, str):
        raise ApiError(400, "malformed_request", f"field {field} must be a string")
    return value


def _issue_session(state, user: dict) -> dict:
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    state.insert_token(token, user["id"])
    return {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "token": token,
    }


def handle_signup(state, body) -> dict:
    """POST /auth/signup -> 201 {user_id, display_name, token}."""
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_request", "body must be a JSON object")
    email = _require_str(body, "email")
    password = _require_str(body, "password")
    display_name = _require_str(body, "display_name")

    if not _EMAIL_RE.match(email):
        raise ApiError(422, "validation_failed", "email must be local@domain")
    if len(password) < 8:
        raise ApiError(422, "validation_failed", "password must be at least 8 characters")

    user_id = "u_" + secrets.token_urlsafe(12)
    # insert_user raises ApiError(409, "email_taken") on a duplicate.
    state.insert_user(user_id, email, hash_password(password), display_name)
    return _issue_session(state, {"id": user_id, "display_name": display_name})


def handle_login(state, body) -> dict:
    """POST /auth/login -> 200 {user_id, display_name, token}."""
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_request", "body must be a JSON object")
    email = _require_str(body, "email")
    password = _require_str(body, "password")

    user = state.user_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        # Unknown email and wrong password share one response: no oracle.
        raise ApiError(401, "unauthenticated", "invalid credentials")
    return _issue_session(state, user)


def authenticate(state, authorization_header):
    """Resolve `Authorization: Bearer <token>` to the user dict.

    Missing, malformed or unknown credentials are all 401 (spec section 5).
    """
    if not authorization_header or not isinstance(authorization_header, str):
        raise ApiError(401, "unauthenticated", "missing bearer token")
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise ApiError(401, "unauthenticated", "malformed authorization header")
    user = state.user_for_token(parts[1])
    if user is None:
        raise ApiError(401, "unauthenticated", "unknown bearer token")
    return user
