"""Signup, login, bearer tokens, scrypt password storage."""

import base64
import hashlib
import hmac
import re
import secrets

import state
from errors import ApiError

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=32, maxmem=64 * 1024 * 1024)
    return "scrypt$%d$%d$%d$%s$%s" % (
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"))


def _verify_password(password, stored):
    try:
        _alg, n, r, p, salt_b64, dig_b64 = stored.split("$")
        expected = base64.b64decode(dig_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
            dklen=len(expected), maxmem=64 * 1024 * 1024)
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _issue_token(user_id):
    token = secrets.token_urlsafe(32)
    state.STATE["tokens"][token] = user_id
    return token


def _new_user_id():
    counters = state.STATE["counters"]
    while True:
        counters["user"] += 1
        uid = "u_%d" % counters["user"]
        if uid not in state.STATE["users"]:
            return uid


def _require_str(body, field):
    if field not in body:
        raise ApiError(422, "validation_failed", "%s is required" % field)
    value = body[field]
    if not isinstance(value, str):
        raise ApiError(400, "malformed_request", "%s must be a string" % field)
    return value


def signup(body):
    email = _require_str(body, "email")
    password = _require_str(body, "password")
    display_name = _require_str(body, "display_name")
    if not _EMAIL_RE.match(email):
        raise ApiError(422, "validation_failed", "email must be local@domain")
    if len(password) < 8:
        raise ApiError(422, "validation_failed",
                       "password must be at least 8 characters")
    if email.lower() in state.STATE["email_index"]:
        raise ApiError(409, "email_taken", "email already registered")
    uid = _new_user_id()
    state.STATE["users"][uid] = {
        "id": uid,
        "email": email,
        "display_name": display_name,
        "password_hash": _hash_password(password),
    }
    state.STATE["email_index"][email.lower()] = uid
    return 201, {
        "user_id": uid,
        "display_name": display_name,
        "token": _issue_token(uid),
    }


def login(body):
    email = _require_str(body, "email")
    password = _require_str(body, "password")
    uid = state.STATE["email_index"].get(email.lower())
    if uid is None:
        raise ApiError(401, "unauthenticated", "unknown email")
    user = state.STATE["users"][uid]
    if not _verify_password(password, user["password_hash"]):
        raise ApiError(401, "unauthenticated", "wrong password")
    return 200, {
        "user_id": uid,
        "display_name": user["display_name"],
        "token": _issue_token(uid),
    }


def require_user(headers):
    header = headers.get("Authorization")
    if header is None:
        raise ApiError(401, "unauthenticated", "missing bearer token")
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise ApiError(401, "unauthenticated", "malformed bearer token")
    uid = state.STATE["tokens"].get(parts[1])
    if uid is None or uid not in state.STATE["users"]:
        raise ApiError(401, "unauthenticated", "unknown token")
    return state.STATE["users"][uid]
