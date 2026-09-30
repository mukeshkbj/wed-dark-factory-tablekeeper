"""Idempotent write pipeline (spec section 7).

The ledger is keyed by (user_id, method, path, key). "Same body" is parsed-JSON
equality: requests are canonicalized with sorted keys before comparison, so
whitespace and member order do not matter.

Claim-and-run happens inside the single state lock, so a concurrent identical
request cannot slip between the ledger lookup and the operation: exactly one
request in such a burst performs the operation and gets 201; the rest replay
the stored response with 200.

A ledger record is written only when the operation succeeds (2xx). Any ApiError
frees the key, so a retry after a 4xx is a first use.

Owned by the engineer seat.
"""
from __future__ import annotations

import json

try:
    from .errors import ApiError
except ImportError:
    from errors import ApiError


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def run(state, user_id, method, path, key, request_obj, op):
    """Resolve the key, then run `op()` exactly once per unique request.

    `op` returns `(status, body)` on success or raises ApiError. Returns the
    `(status, body)` the caller should send.
    """
    request_json = canonical(request_obj)
    with state.lock:
        record = state.idem_get(user_id, method, path, key)
        if record is not None:
            stored_request, _status, stored_response = record
            if stored_request != request_json:
                raise ApiError(409, "idempotency_key_reuse",
                               "key already used with a different request")
            # Replay: the original response body, verbatim, at status 200.
            return 200, json.loads(stored_response)
        status, body = op()
        state.idem_put(user_id, method, path, key, request_json, status,
                       canonical(body))
        return status, body
