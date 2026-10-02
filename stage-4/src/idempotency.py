"""Idempotency-Key resolution (spec section 7).

Keys are scoped per user. A record is stored only for successful (<400)
outcomes, so a key whose first use failed 4xx is reusable. A replay is the
same user + key + method + path + identical parsed JSON body; it returns
200 with the ORIGINAL response value. Same key + same path but different
body -> 409 idempotency_key_reuse. Same key on a different path is a new
request and must succeed normally.

Called inside state.LOCK, so concurrent identical requests resolve
atomically: exactly one 201, the rest get the stored body at 200.
"""

import state
from errors import ApiError


def execute(user_id, method, path, key, body, fn):
    bucket = state.STATE["idempotency"].get(user_id, {})
    records = bucket.get(key, [])
    for rec in records:
        if rec["method"] == method and rec["path"] == path:
            if rec["body"] == body:
                return 200, rec["response"]
            raise ApiError(409, "idempotency_key_reuse",
                           "key already used with a different body")
    status, response = fn()
    if status < 400:
        state.STATE["idempotency"].setdefault(user_id, {}).setdefault(
            key, []).append({
                "method": method, "path": path,
                "body": body, "response": response,
            })
    return status, response
