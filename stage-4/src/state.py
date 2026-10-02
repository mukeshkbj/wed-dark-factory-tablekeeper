"""Process-wide service state.

Everything lives in one JSON-native dict behind ONE re-entrant lock.
Every check-and-act (availability scan -> create, moves batch, cancel,
import, export snapshot) runs as a single critical section, which makes
concurrent requests linearizable. All values are plain JSON types so
export = deepcopy and import = validate + swap.
"""

import copy
import threading

LOCK = threading.RLock()

STATE = {
    "users": {},            # user_id -> {id,email,password_hash,display_name}
    "email_index": {},      # lowercased email -> user_id
    "tokens": {},           # token -> user_id
    "restaurants": {},      # restaurant_id -> fixture object (verbatim)
    "restaurant_order": [], # fixture order
    "reservations": {},     # reservation_id -> record (see reservations.py)
    "reference_index": {},  # reference -> reservation_id
    "policies": {},         # restaurant_id -> [published policy]
    "series": {},           # series_id -> recurring agreement record
    "plans": {},            # plan_id -> pending/applied replan
    "closures": {},         # restaurant_id -> [applied table closure]
    "restaurant_revisions": {},  # restaurant_id -> internal write count
    "idempotency": {},      # user_id -> key -> {"scope": {m p: {body,status,response}}}
    "counters": {"user": 0, "reservation": 0, "series": 0, "plan": 0},
}


def reset_all():
    with LOCK:
        for key, val in _fresh().items():
            STATE[key] = val


def _fresh():
    return {
        "users": {},
        "email_index": {},
        "tokens": {},
        "restaurants": {},
        "restaurant_order": [],
        "reservations": {},
        "reference_index": {},
        "policies": {},
        "series": {},
        "plans": {},
        "closures": {},
        "restaurant_revisions": {},
        "idempotency": {},
        "counters": {"user": 0, "reservation": 0, "series": 0,
                     "plan": 0},
    }


def export_state():
    with LOCK:
        return copy.deepcopy(STATE)


def import_state(new_state):
    with LOCK:
        STATE.clear()
        STATE.update(copy.deepcopy(new_state))
