#!/usr/bin/env python3
"""tk-verifier stage-1 black-box checks (spec-derived; stdlib only).

Usage: python checks.py --base-url http://localhost:8080 [--keep-going]
Every request has a hard timeout; a hang fails the run.
"""
import argparse, json, re, sys, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8080"
REQ_TIMEOUT = 12          # generous outer bound; >5s non-reset latency flagged separately
RESULTS = []              # (cid, ok, detail)
FIVE_XX = []              # any 5xx observed

def call(method, path, body=None, raw=None, token=None, idem=None,
         extra_headers=None, timeout=REQ_TIMEOUT):
    url = BASE + path
    data, h = None, {}
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode()
        h["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    if idem is not None:
        h["Idempotency-Key"] = idem
    if extra_headers:
        h.update(extra_headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            st, hd, b = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        st, hd, b = e.code, dict(e.headers), e.read()
    except Exception as e:
        return -1, {}, str(e).encode(), time.monotonic() - t0
    return st, hd, b, time.monotonic() - t0

def j(b):
    try:
        return json.loads(b)
    except Exception:
        return None

def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)

def note(cid, detail):  # observation, never counted
    print("NOTE", cid, "-", detail, flush=True)

def err_code(body):
    x = j(body)
    return (x or {}).get("error", {}).get("code")

def err_shape(cid, st, body):
    x = j(body)
    ok = isinstance(x, dict) and isinstance(x.get("error"), dict) and \
         isinstance(x["error"].get("code"), str) and isinstance(x["error"].get("message"), str)
    if not ok:
        expect(cid + ":shape", False, f"error body shape wrong st={st} body={body[:160]!r}")
        return False
    return True

def check_status(cid, st, want, body=b"", code=None, latency=None, max_lat=5.0):
    if st >= 500 or st == -1:
        FIVE_XX.append((cid, st))
    ok = (st == want) if not isinstance(want, (list, tuple)) else (st in want)
    if st >= 400 and ok:
        err_shape(cid, st, body)
    if code is not None and st == want:
        got = err_code(body)
        if got != code:
            expect(cid, False, f"want code={code} got code={got} st={st} body={body[:160]!r}")
            return False
    if latency is not None and latency > max_lat:
        expect(cid + ":lat", False, f"latency {latency:.2f}s > {max_lat}s")
    expect(cid, ok, f"st={st} want={want} code={err_code(body) if st>=400 else '-'}")
    return ok

WEEKDAYS = ["mon","tue","wed","thu","fri","sat","sun"]

def fixture_base():
    return {
        "users": [
            {"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"},
            {"id":"u_bob","email":"bob@example.com","password":"second horse","display_name":"Bob"},
        ],
        "restaurants": [
            {"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin",
             "slot_minutes":30,"reservation_duration_minutes":90,"cancellation_cutoff_minutes":120,
             "opening_hours":[{"weekday":"thu","opens":"18:00","closes":"23:00"},
                              {"weekday":"fri","opens":"18:00","closes":"23:30"}],
             "tables":[{"id":"t_1","label":"1","capacity":2},
                       {"id":"t_2","label":"2","capacity":4}]},
            {"id":"r_ops","name":"Ops Haus","timezone":"UTC",
             "slot_minutes":15,"reservation_duration_minutes":60,"cancellation_cutoff_minutes":120,
             "opening_hours":[{"weekday":w,"opens":"00:00","closes":"23:59"} for w in WEEKDAYS],
             "tables":[{"id":"t_a","label":"A","capacity":4},
                       {"id":"t_b","label":"B","capacity":4},
                       {"id":"t_c","label":"C","capacity":8}]},
            {"id":"r_berlin","name":"DST Berlin","timezone":"Europe/Berlin",
             "slot_minutes":30,"reservation_duration_minutes":90,"cancellation_cutoff_minutes":60,
             "opening_hours":[{"weekday":"sun","opens":"00:00","closes":"06:00"}],
             "tables":[{"id":"tb_1","label":"1","capacity":4}]},
            {"id":"r_nyc","name":"DST NYC","timezone":"America/New_York",
             "slot_minutes":30,"reservation_duration_minutes":90,"cancellation_cutoff_minutes":60,
             "opening_hours":[{"weekday":"sun","opens":"00:00","closes":"06:00"}],
             "tables":[{"id":"tn_1","label":"1","capacity":4}]},
        ],
        "reservations": [],
    }

def utc_local(minutes_from_now):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)).strftime("%Y-%m-%dT%H:%M")

def reset(fx=None, cid="C-RT-x"):
    st, hd, b, dt = call("POST", "/_test/reset", body=fx if fx is not None else fixture_base(), timeout=15)
    if st != 204:
        expect(cid, False, f"reset st={st} body={b[:200]!r}")
        return False
    return True

def login(email, pw):
    st, hd, b, dt = call("POST", "/auth/login", body={"email":email,"password":pw})
    return st, j(b)

def signup(email, pw, name):
    st, hd, b, dt = call("POST", "/auth/signup", body={"email":email,"password":pw,"display_name":name})
    return st, j(b)

KEY = [0]
def key(prefix="k"):
    KEY[0] += 1
    return f"{prefix}-{int(time.time())}-{KEY[0]}"

# ---------------- runtime / auth / error surface ----------------

def sec_runtime():
    st, hd, b, dt = call("GET", "/health")
    check_status("C-RT-1", st, 200, b)
    expect("C-RT-1b", j(b) == {"status": "ok"}, f"body={b[:120]!r}")
    st, hd, b, dt = call("POST", "/_test/reset", body=fixture_base())
    check_status("C-RT-2", st, 204, b, latency=dt, max_lat=10.0)
    st, hd, b, dt = call("POST", "/_test/reset", body=fixture_base())
    check_status("C-RT-3", st, 204, b)
    # reset determinism: identical observable state after repeat resets
    st1, _, b1, _ = call("GET", "/restaurants/r_anker")
    call("POST", "/_test/reset", body=fixture_base())
    st2, _, b2, _ = call("GET", "/restaurants/r_anker")
    expect("C-RT-4", st1 == st2 == 200 and j(b1) == j(b2), "restaurant identical across resets")
    # residue check: sign up, reset, same email must be free again
    signup("residue@x.com", "password1", "Res")
    call("POST", "/_test/reset", body=fixture_base())
    st, bd = login("residue@x.com", "password1")
    check_status("C-RT-4b", st, 401, json.dumps(bd).encode(), code="unauthenticated")
    # content-type
    st, hd, b, dt = call("GET", "/restaurants")
    ct = hd.get("Content-Type") or hd.get("content-type") or ""
    expect("C-RT-5", "application/json" in ct, f"content-type={ct!r}")

def sec_auth():
    reset()
    st, bd = login("ada@example.com", "correct horse")
    check_status("C-AU-0", st, 200, json.dumps(bd).encode())
    ada = (bd or {}).get("token")
    expect("C-AU-0b", bool(ada) and bd.get("user_id") == "u_ada", "seeded user token+id")
    st, bd = signup("caro@example.com", "password9", "Caro")
    check_status("C-AU-1", st, 201, json.dumps(bd).encode())
    caro = (bd or {}).get("token")
    st, bd = login("caro@example.com", "password9")
    check_status("C-AU-2", st, 200, json.dumps(bd).encode())
    st, hd, b, _ = call("POST", "/auth/signup", body={"email":"caro@example.com","password":"password9","display_name":"X"})
    check_status("C-AU-3", st, 409, b, code="email_taken")
    st, hd, b, _ = call("POST", "/auth/signup", body={"email":"new@x.com","password":"short","display_name":"X"})
    check_status("C-AU-3b", st, 422, b, code="validation_failed")
    for em in ("noatsign", "a@", "@b.com", "a b@c.com"):
        st, hd, b, _ = call("POST", "/auth/signup", body={"email":em,"password":"password9","display_name":"X"})
        check_status("C-AU-3c", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("POST", "/auth/login", body={"email":"ada@example.com","password":"wrong"})
    check_status("C-AU-3d", st, 401, b, code="unauthenticated")
    st, hd, b, _ = call("POST", "/auth/login", body={"email":"ghost@x.com","password":"password9"})
    check_status("C-AU-3e", st, 401, b, code="unauthenticated")
    # bearer required sweep on protected endpoints
    for m, p in [("GET","/reservations"), ("POST","/reservations"),
                 ("GET","/reservations/ABC123"), ("PATCH","/reservations/ABC123"),
                 ("POST","/reservations/ABC123/cancel"), ("POST","/reservation-moves")]:
        st, hd, b, _ = call(m, p, body={} if m != "GET" else None)
        check_status("C-AU-4", st, 401, b, code="unauthenticated")
    st, hd, b, _ = call("GET", "/reservations", extra_headers={"Authorization": "Bearer nope.invalid.token"})
    check_status("C-AU-4b", st, 401, b, code="unauthenticated")
    # multiple tokens concurrently valid
    st, b2 = login("ada@example.com", "correct horse")
    ada2 = (b2 or {}).get("token")
    s1, _, _, _ = call("GET", "/reservations", token=ada)
    s2, _, _, _ = call("GET", "/reservations", token=ada2)
    expect("C-AU-5", s1 == 200 and s2 == 200 and ada != ada2 or (s1 == s2 == 200), f"tokens both valid s1={s1} s2={s2}")
    # public endpoints without token
    for p in ["/restaurants", "/restaurants/r_anker", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=2"]:
        st, hd, b, _ = call("GET", p)
        check_status("C-AU-6", st, 200, b)

def sec_errors():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    book = {"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":4}
    # parse beats auth: malformed body, no token -> 400
    st, hd, b, _ = call("POST", "/reservations", raw=b"{not json")
    check_status("C-ERR-1", st, 400, b, code="malformed_request")
    # wrong JSON type field -> 400
    bad = dict(book); bad["restaurant_id"] = 123
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-ERR-2", st, 400, b, code="malformed_request")
    # non-object JSON body -> 400 or 422, never 5xx
    for raw in ('123', '[1,2]', '"str"', 'null'):
        st, hd, b, _ = call("POST", "/reservations", raw=raw, token=ada, idem=key())
        check_status("C-ERR-3", st, (400, 422), b)
    # missing required field -> 422
    for f in ("restaurant_id", "table_id", "starts_at_local", "party_size"):
        bad = {k: v for k, v in book.items() if k != f}
        st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
        check_status("C-ERR-4", st, 422, b, code="validation_failed")
    # over-range/invalid-format values of correct type -> 422
    bad = dict(book); bad["starts_at_local"] = "2026-13-40T19:00"
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-ERR-5", st, 422, b)
    # party_size type/format precedence: string/bool/float/object -> 422 (NOT 400)
    for v in ("4", True, 4.0, {"n": 4}, -1, 0):
        bad = dict(book); bad["party_size"] = v
        st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
        check_status("C-ERR-8", st, 422, b, code="validation_failed")
    # extreme-precision number literal: correct JSON type, non-integer value -> 422
    raw = b'{"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":1000.00000000000000001}'
    st, hd, b, _ = call("POST", "/reservations", raw=raw, token=ada, idem=key())
    check_status("C-ERR-8x", st, 422, b)
    # non-bare starts_at_local -> 422
    for v in ("2026-09-24T19:00+02:00", "2026-09-24T19:00Z", "2026-09-24 19:00",
              "2026-09-24", "2026-09-24T19:00:00", "19:00"):
        bad = dict(book); bad["starts_at_local"] = v
        st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
        check_status("C-ERR-9", st, 422, b, code="validation_failed")
    # unknown body fields ignored
    good = dict(book); good["zzz_unknown"] = {"x": [1]}
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, idem=key())
    check_status("C-IGN-1", st, 201, b)
    # unknown query params ignored
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=2&bogus=1&x=y")
    check_status("C-IGN-2", st, 200, b)
    # oversized fixture id -> 4xx (ruling: 422 + state unchanged)
    fx = fixture_base(); fx["restaurants"][0]["id"] = "x" * 65
    st, hd, b, _ = call("POST", "/_test/reset", body=fx)
    check_status("C-IGN-3", st, (400, 422), b)
    reset()

# ---------------- API surface / availability / booking ----------------

RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

def sec_api():
    reset()
    st, hd, b, _ = call("GET", "/restaurants")
    check_status("C-API-1", st, 200, b)
    rs = (j(b) or {}).get("restaurants", [])
    expect("C-API-1b", all(set(r.keys()) >= {"id","name","timezone"} for r in rs) and len(rs) == 4,
           f"list shape n={len(rs)}")
    st, hd, b, _ = call("GET", "/restaurants/r_anker")
    check_status("C-API-2", st, 200, b)
    r = j(b) or {}
    expect("C-API-2b", all(k in r for k in ("slot_minutes","reservation_duration_minutes",
           "cancellation_cutoff_minutes","opening_hours","tables")), f"detail keys={sorted(r)}")
    st, hd, b, _ = call("GET", "/restaurants/nope")
    check_status("C-API-2c", st, 404, b, code="not_found")
    # no creation endpoints
    st, hd, b, _ = call("POST", "/restaurants", body={"id":"x"})
    check_status("C-API-0", st, (404, 405), b)

def sec_availability():
    reset()
    # missing params
    for q in ["restaurant_id=r_anker&date=2026-09-24",
              "restaurant_id=r_anker&party_size=2",
              "date=2026-09-24&party_size=2", ""]:
        st, hd, b, _ = call("GET", "/availability?" + q)
        check_status("C-AV-1", st, 422, b, code="validation_failed")
    # integer query-param lexical rule
    for ps in ("1e9", "4.0", "+4", "-1", "x", "0x4", " 4", "4 "):
        st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_anker&date=2026-09-24&party_size={ps}")
        check_status("C-AV-6", st, 422, b, code="validation_failed")
    for d in ("2026-13-40", "24-09-2026", "2026/09/24", "x"):
        st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_anker&date={d}&party_size=2")
        check_status("C-AV-6b", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("GET", "/availability?restaurant_id=nope&date=2026-09-24&party_size=2")
    check_status("C-AV-6c", st, (404, 422), b)   # ruling G-4
    # grid enumeration: thu 18:00-23:00, slot 30, dur 90 -> last slot 21:30
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=2")
    check_status("C-AV-2", st, 200, b)
    slots = [s["starts_at_local"] for s in (j(b) or {}).get("slots", [])]
    want = ["2026-09-24T18:00","2026-09-24T18:30","2026-09-24T19:00","2026-09-24T19:30",
            "2026-09-24T20:00","2026-09-24T20:30","2026-09-24T21:00","2026-09-24T21:30"]
    expect("C-AV-2b", slots == want, f"grid {slots} != {want}")
    offs = [s["starts_at"] for s in (j(b) or {}).get("slots", [])]
    expect("C-AV-2c", all(o.endswith("+02:00") for o in offs) and
           all(RFC3339.match(o) for o in offs), f"offsets {offs[:3]}")
    expect("C-AV-2d", (j(b) or {}).get("timezone") == "Europe/Berlin", "echo timezone")
    # capacity filter + fixture order: party 2 -> t_1,t_2 ; party 4 -> t_2 only ; party 9 -> none
    s2 = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {}).get("slots", [])}
    expect("C-AV-3", s2.get("2026-09-24T19:00") == ["t_1","t_2"], f"p2 {s2.get('2026-09-24T19:00')}")
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=4")
    s4 = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {}).get("slots", [])}
    expect("C-AV-4", s4.get("2026-09-24T19:00") == ["t_2"], f"p4 {s4.get('2026-09-24T19:00')}")
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=9")
    s9 = (j(b) or {}).get("slots", [])
    expect("C-AV-5", len(s9) == 8 and all(x["available_table_ids"] == [] for x in s9),
           "slots listed with empty table lists")
    # closed day
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker&date=2026-09-26&party_size=2")
    expect("C-AV-7", (j(b) or {}).get("slots") == [], f"sat closed {b[:80]!r}")

def sec_booking():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    good = {"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":4}
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, idem=key())
    check_status("C-BK-1", st, 201, b)
    r = j(b) or {}
    need = {"reservation_id","reference","restaurant_id","table_id","party_size","status",
            "starts_at_local","starts_at","ends_at","created_at"}
    expect("C-BK-1b", need <= set(r) and r["status"] == "confirmed" and r["party_size"] == 4,
           f"fields {sorted(r)}")
    expect("C-BK-1c", r.get("starts_at") == "2026-09-24T19:00:00+02:00" and
           r.get("ends_at") == "2026-09-24T20:30:00+02:00" and
           RFC3339.match(r.get("created_at","")), f"times {r.get('starts_at')} {r.get('ends_at')} {r.get('created_at')}")
    expect("C-BK-2", isinstance(r.get("reference"), str) and
           re.match(r"^[A-Z0-9]{6,12}$", r["reference"]), f"ref {r.get('reference')!r}")
    # past booking allowed (r_ops UTC, yesterday)
    past = {"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(-24*60),"party_size":2}
    st, hd, b, _ = call("POST", "/reservations", body=past, token=ada, idem=key())
    check_status("C-PST-1", st, 201, b)

def sec_booking_errors():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    base = {"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":4}
    st, hd, b, _ = call("POST", "/reservations", body=base, token=ada, idem=key())
    assert st == 201
    # overlap -> 409
    for t in ("19:30", "20:00", "19:00"):
        bad = dict(base); bad["starts_at_local"] = f"2026-09-24T{t}"
        st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
        check_status("C-BK-3", st, 409, b, code="table_unavailable")
    # half-open edges: 20:30 and 17:30? (17:30 off-hours; use 20:30 end-touch and 17:59.. skip) 
    bad = dict(base); bad["starts_at_local"] = "2026-09-24T20:30"
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BND-1", st, 201, b, code=None)
    # off-grid
    bad = dict(base); bad["starts_at_local"] = "2026-09-24T19:15"
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BK-4", st, 422, b, code="not_on_slot_grid")
    # outside hours / end after closes
    for t in ("17:00", "22:00"):
        bad = dict(base); bad["starts_at_local"] = f"2026-09-24T{t}"
        st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
        check_status("C-BK-5", st, 422, b, code="outside_opening_hours")
    # capacity
    bad = dict(base); bad["party_size"] = 5
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BK-6", st, 422, b, code="party_exceeds_capacity")
    # 404s
    bad = dict(base); bad["restaurant_id"] = "nope"; bad["starts_at_local"] = "2026-09-25T19:00"
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BK-7", st, 404, b, code="not_found")
    bad = dict(base); bad["table_id"] = "nope"; bad["starts_at_local"] = "2026-09-25T19:00"
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BK-8", st, 404, b, code="not_found")
    bad = dict(base); bad["restaurant_id"] = "r_ops"; bad["table_id"] = "t_2"  # t_2 belongs to r_anker
    bad["starts_at_local"] = utc_local(24*60)
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=key())
    check_status("C-BK-9", st, 404, b, code="not_found")

# ---------------- list / cancel / patch / permissions ----------------

def sec_list_cancel_patch():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    _, bd2 = login("bob@example.com", "second horse"); bob = bd2["token"]
    # list shape + ordering (starts_at desc, confirmed+cancelled)
    t1, t2 = utc_local(24*60), utc_local(30*60)
    r1 = call("POST", "/reservations", body={"restaurant_id":"r_ops","table_id":"t_a",
              "starts_at_local":t1,"party_size":2}, token=ada, idem=key())
    r2 = call("POST", "/reservations", body={"restaurant_id":"r_ops","table_id":"t_b",
              "starts_at_local":t2,"party_size":2}, token=ada, idem=key())
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    check_status("C-LST-1", st, 200, b)
    lst = (j(b) or {}).get("reservations", [])
    expect("C-LST-1b", len(lst) == 2 and lst[0]["starts_at"] >= lst[1]["starts_at"], "desc order")
    st, hd, b, _ = call("GET", "/reservations", token=bob)
    expect("C-LST-2", (j(b) or {}).get("reservations") == [], "bob sees none")
    ref1 = (j(r1[2]) or {}).get("reference")
    # foreign access -> 404 everywhere
    for m, p in [("GET", f"/reservations/{ref1}"), ("PATCH", f"/reservations/{ref1}"),
                 ("POST", f"/reservations/{ref1}/cancel")]:
        st, hd, b, _ = call(m, p, body={"party_size":3} if m == "PATCH" else None, token=bob)
        check_status("C-PRM-1", st, 404, b, code="not_found")
    # cancel frees slot immediately
    d = t1[:10]
    st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_ops&date={d}&party_size=2")
    before = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {})["slots"]}
    st, hd, b, _ = call("POST", f"/reservations/{ref1}/cancel", token=ada)
    check_status("C-CXL-1", st, 200, b)
    expect("C-CXL-1b", (j(b) or {}).get("status") == "cancelled", f"status {b[:100]!r}")
    st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_ops&date={d}&party_size=2")
    after = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {})["slots"]}
    expect("C-CXL-2", "t_a" in after.get(t1, []) and "t_a" not in before.get(t1, []),
           f"freed: before={before.get(t1)} after={after.get(t1)}")
    # double cancel -> 200 current state
    st, hd, b, _ = call("POST", f"/reservations/{ref1}/cancel", token=ada)
    check_status("C-CXL-3", st, 200, b)
    expect("C-CXL-3b", (j(b) or {}).get("status") == "cancelled", "still cancelled")
    # cancelled shows in list
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    expect("C-LST-3", any(x.get("reference") == ref1 and x.get("status") == "cancelled"
           for x in (j(b) or {}).get("reservations", [])), "cancelled listed")
    # PATCH cancelled -> 409 reservation_cancelled
    st, hd, b, _ = call("PATCH", f"/reservations/{ref1}", body={"party_size":3}, token=ada)
    check_status("C-PAT-1", st, 409, b, code="reservation_cancelled")
    # PATCH success: move t_b booking to t_c at same time; releases t_b, reserves t_c
    ref2 = (j(r2[2]) or {}).get("reference")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", body={"table_id":"t_c"}, token=ada)
    check_status("C-PAT-2", st, 200, b)
    pr = j(b) or {}
    expect("C-PAT-2b", pr.get("table_id") == "t_c" and pr.get("reference") == ref2 and
           pr.get("reservation_id") == (j(r2[2]) or {}).get("reservation_id"),
           "identity+reference preserved")
    d2 = t2[:10]
    st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_ops&date={d2}&party_size=2")
    m = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {})["slots"]}
    expect("C-PAT-3", "t_b" in m.get(t2, []) and "t_c" not in m.get(t2, []),
           f"old freed new held: {m.get(t2)}")
    # PATCH failure atomicity: patch t_c onto occupied t_c? patch onto t_a at t2
    call("POST", "/reservations", body={"restaurant_id":"r_ops","table_id":"t_a",
         "starts_at_local":t2,"party_size":2}, token=ada, idem=key())
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", body={"table_id":"t_a"}, token=ada)
    check_status("C-PAT-5", st, 409, b, code="table_unavailable")
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    expect("C-PAT-5b", (j(b) or {}).get("table_id") == "t_c", "failed PATCH left original")
    # PATCH validation identical to create (bad party_size)
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", body={"party_size":"x"}, token=ada)
    check_status("C-PAT-6", st, 422, b)
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    expect("C-PAT-6b", (j(b) or {}).get("party_size") == 2, "failed PATCH kept values")
    # no-op patch observation
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", body={}, token=ada)
    note("C-PAT-G9", f"empty PATCH -> {st}")

def sec_cutoff():
    # seeded reservations relative to NOW on r_ops (UTC, cutoff 120)
    fx = fixture_base()
    near, far = utc_local(60), utc_local(180)
    fx["reservations"] = [
        {"id":"rs_past","reference":"PAST01","user_id":"u_ada","restaurant_id":"r_ops",
         "table_id":"t_a","starts_at_local":utc_local(-60),"party_size":2},
        {"id":"rs_near","reference":"NEAR01","user_id":"u_ada","restaurant_id":"r_ops",
         "table_id":"t_b","starts_at_local":near,"party_size":2},
        {"id":"rs_far","reference":"FAR001","user_id":"u_ada","restaurant_id":"r_ops",
         "table_id":"t_c","starts_at_local":far,"party_size":2},
    ]
    reset(fx)
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    # seeded booking visible
    st, hd, b, _ = call("GET", "/reservations/PAST01", token=ada)
    check_status("C-FX-2", st, 200, b)
    st, hd, b, _ = call("POST", "/reservations/PAST01/cancel", token=ada)
    check_status("C-CXL-4", st, 409, b, code="cutoff_passed")
    st, hd, b, _ = call("POST", "/reservations/NEAR01/cancel", token=ada)
    check_status("C-CXL-4b", st, 409, b, code="cutoff_passed")
    st, hd, b, _ = call("POST", "/reservations/FAR001/cancel", token=ada)
    check_status("C-CXL-5", st, 200, b)
    # PATCH within cutoff -> 409 (current start)
    st, hd, b, _ = call("PATCH", "/reservations/NEAR01", body={"party_size":3}, token=ada)
    check_status("C-PAT-7", st, 409, b, code="cutoff_passed")
    # occupancy still held for cutoff-blocked booking
    d = near[:10]
    st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_ops&date={d}&party_size=2")
    m = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {})["slots"]}
    expect("C-CXL-6", "t_b" not in m.get(near, []), f"near slot still occupied {m.get(near)}")
    # invalid fixture handling
    fx2 = fixture_base(); fx2["restaurants"][0]["opening_hours"][0]["weekday"] = "noday"
    st, hd, b, _ = call("POST", "/_test/reset", body=fx2)
    check_status("C-FX-1", st, (400, 422), b)
    st, hd, b, _ = call("GET", "/restaurants/r_ops")
    expect("C-FX-1b", st == 200, "state unchanged after invalid fixture")
    reset()

# ---------------- idempotency ----------------

def sec_idem():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    _, bd2 = login("bob@example.com", "second horse"); bob = bd2["token"]
    good = {"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(26*60),"party_size":2}
    # missing / empty header
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada)
    check_status("C-IDM-1a", st, 400, b, code="missing_idempotency_key")
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, extra_headers={"Idempotency-Key": ""})
    check_status("C-IDM-1b", st, 400, b, code="missing_idempotency_key")
    st, hd, b, _ = call("POST", "/reservation-moves", body={"moves":[]}, token=ada)
    check_status("C-IDM-1c", st, 400, b, code="missing_idempotency_key")
    # key length bounds
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, idem="k" * 256)
    check_status("C-IDM-2", st, 422, b, code="validation_failed")
    k1 = "k" * 255
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, idem=k1)
    check_status("C-IDM-2b", st, 201, b)
    orig = j(b); ref = orig.get("reference")
    # replay: identical body, reordered key order in JSON -> 200 identical body
    reordered = json.dumps({k2: good[k2] for k2 in reversed(list(good))}).encode()
    st, hd, b, _ = call("POST", "/reservations", raw=reordered, token=ada, idem=k1)
    check_status("C-IDM-7", st, 200, b)
    expect("C-IDM-7b", j(b) == orig, "replay body identical as JSON value")
    # different body -> 409 even when new body is invalid (idempotency before validation)
    bad = {"restaurant_id": 999}
    st, hd, b, _ = call("POST", "/reservations", body=bad, token=ada, idem=k1)
    check_status("C-IDM-6", st, 409, b, code="idempotency_key_reuse")
    st, hd, b, _ = call("POST", "/reservations", body=dict(good, party_size=3), token=ada, idem=k1)
    check_status("C-IDM-3", st, 409, b, code="idempotency_key_reuse")
    # key freed after 4xx
    kf = key("fail")
    st, hd, b, _ = call("POST", "/reservations", body=dict(good, party_size=0), token=ada, idem=kf)
    check_status("C-IDM-8", st, 422, b)
    good2 = dict(good, table_id="t_b")
    st, hd, b, _ = call("POST", "/reservations", body=good2, token=ada, idem=kf)
    check_status("C-IDM-8b", st, 201, b)
    # per-user scope: same key string, different user -> independent 201
    ks = key("shared")
    goodA = dict(good, table_id="t_c")
    st, hd, b, _ = call("POST", "/reservations", body=goodA, token=ada, idem=ks)
    check_status("C-IDM-4", st, 201, b)
    goodB = dict(good, table_id="t_c", starts_at_local=utc_local(40*60))
    st, hd, b, _ = call("POST", "/reservations", body=goodB, token=bob, idem=ks)
    check_status("C-IDM-4b", st, 201, b)
    # per-path scope: same key on different path is a new request
    kp = key("paths")
    good3 = dict(good, table_id="t_b", starts_at_local=utc_local(50*60))
    st, hd, b, _ = call("POST", "/reservations", body=good3, token=ada, idem=kp)
    check_status("C-IDM-5", st, 201, b)
    ref3 = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=kp,
                        body={"moves":[{"reference":ref3,"party_size":3}]})
    check_status("C-IDM-5b", st, 201, b)   # must not be idempotency_key_reuse
    # replay after cancel returns ORIGINAL confirmed response, no state change
    call("POST", f"/reservations/{ref}/cancel", token=ada)
    st, hd, b, _ = call("POST", "/reservations", body=good, token=ada, idem=k1)
    check_status("C-IDM-9", st, 200, b)
    expect("C-IDM-9b", j(b) == orig and (j(b) or {}).get("status") == "confirmed",
           "replay returns original confirmed body after cancel")
    # whitespace-only key -> observation
    st, hd, b, _ = call("POST", "/reservations", body=dict(good, table_id="t_c", starts_at_local=utc_local(60*60)),
                        token=ada, extra_headers={"Idempotency-Key": " "})
    note("C-IDM-G10", f"whitespace key -> {st} {err_code(b)}")

# ---------------- concurrency ----------------

def sec_concurrency():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    N = 25
    # 25 identical requests, same key -> exactly one 201, rest 200, one booking
    kx = key("race")
    body = {"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(72*60),"party_size":2}
    barrier = threading.Barrier(N)
    def one():
        barrier.wait()
        return call("POST", "/reservations", body=body, token=ada, idem=kx)
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(lambda _: one(), range(N)))
    sts = [r[0] for r in rs]
    bodies = [j(r[2]) for r in rs]
    n201 = sts.count(201); n200 = sts.count(200)
    expect("C-CON-1", n201 == 1 and n200 == N - 1, f"201x{n201} 200x{n200} sts={sts}")
    first = next(bd2 for s, bd2 in zip(sts, bodies) if s == 201)
    expect("C-CON-1b", all(bd2 == first for bd2 in bodies), "all bodies identical to winner")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    expect("C-CON-1c", len((j(b) or {}).get("reservations", [])) == 1, "exactly one booking")
    # 25 conflicting bookings (different keys, same table+slot) -> exactly one wins
    body2 = {"restaurant_id":"r_ops","table_id":"t_b","starts_at_local":utc_local(80*60),"party_size":2}
    ks2 = [key("cf") for _ in range(N)]
    barrier = threading.Barrier(N)
    def one2(i):
        barrier.wait()
        return call("POST", "/reservations", body=body2, token=ada, idem=ks2[i])
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(one2, range(N)))
    sts = [r[0] for r in rs]
    codes = [err_code(r[2]) for r in rs]
    expect("C-CON-2", sts.count(201) == 1 and sts.count(409) == N - 1 and
           all(c in (None, "table_unavailable") for c in codes), f"sts={sts} codes={codes}")
    # conservation: table held once at the slot
    d = body2["starts_at_local"][:10]
    st, hd, b, _ = call("GET", f"/availability?restaurant_id=r_ops&date={d}&party_size=2")
    m = {s["starts_at_local"]: s["available_table_ids"] for s in (j(b) or {})["slots"]}
    expect("C-CON-3", "t_b" not in m.get(body2["starts_at_local"], []), "winner occupies slot")

# ---------------- reservation moves ----------------

def book(ada, table, when, party=2, k=None):
    st, hd, b, _ = call("POST", "/reservations",
        body={"restaurant_id":"r_ops","table_id":table,"starts_at_local":when,"party_size":party},
        token=ada, idem=k or key())
    return st, j(b) or {}

def sec_moves():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    _, bd2 = login("bob@example.com", "second horse"); bob = bd2["token"]
    T = utc_local(100*60); T2 = utc_local(120*60); T3 = utc_local(140*60)
    r1 = book(ada, "t_a", T)[1]; r2 = book(ada, "t_b", T)[1]
    rf1, rf2 = r1.get("reference"), r2.get("reference")
    # auth/key requirements
    st, hd, b, _ = call("POST", "/reservation-moves", body={"moves":[{"reference":rf1,"party_size":3}]})
    check_status("C-MV-1", st, 401, b, code="unauthenticated")
    # shape errors
    for mv in ([], [{"reference":rf1}]*2 + [{"reference":rf2}]*7,  # 9 items
               [{"reference":rf1},{"reference":rf1}],              # dup refs
               [{"reference":123}]):                               # non-string ref
        st, hd, b, _ = call("POST", "/reservation-moves", body={"moves":mv}, token=ada, idem=key())
        check_status("C-MV-2", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("POST", "/reservation-moves", body={"moves":"x"}, token=ada, idem=key())
    check_status("C-MV-2d", st, (400, 422), b)  # G-3
    # foreign / unknown refs
    rb = book(bob, "t_c", T3)[1]
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rb.get("reference"),"party_size":3}]}, token=ada, idem=key())
    check_status("C-MV-3", st, 404, b, code="not_found")
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":"NOPE99","party_size":3}]}, token=ada, idem=key())
    check_status("C-MV-3b", st, 404, b, code="not_found")
    # mixed restaurants -> 422
    _, bd3 = login("ada@example.com", "correct horse")
    r_ank = call("POST", "/reservations", body={"restaurant_id":"r_anker","table_id":"t_1",
        "starts_at_local":"2026-09-25T19:00","party_size":2}, token=ada, idem=key())
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rf1,"party_size":3},
                       {"reference":(j(r_ank[2]) or {}).get("reference"),"party_size":2}]},
        token=ada, idem=key())
    check_status("C-MV-5", st, 422, b, code="validation_failed")
    # the classic swap: r1->t_b, r2->t_a in one batch
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rf1,"table_id":"t_b"},{"reference":rf2,"table_id":"t_a"}]},
        token=ada, idem=key())
    check_status("C-MV-12", st, 201, b)
    mv = (j(b) or {}).get("reservations", [])
    expect("C-MV-12b", len(mv) == 2 and mv[0].get("reference") == rf1 and
           mv[0].get("table_id") == "t_b" and mv[1].get("table_id") == "t_a",
           f"swap result {[ (x.get('reference'),x.get('table_id')) for x in mv ]}")
    # atomicity: batch where 2nd move collides with unlisted booking -> all-or-nothing
    r3 = book(ada, "t_c", T2)[1]; rf3 = r3.get("reference")
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rf1,"table_id":"t_a"},          # legal alone
                       {"reference":rf3,"table_id":"t_a","starts_at_local":T}]},  # collides w/ rf2 at t_a
        token=ada, idem=key())
    check_status("C-MV-13", st, 409, b, code="table_unavailable")
    st, hd, b, _ = call("GET", f"/reservations/{rf1}", token=ada)
    expect("C-MV-13b", (j(b) or {}).get("table_id") == "t_b", "failed batch: first move rolled back")
    # input-order precedence: first move's non-occupancy error wins
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rf1,"party_size":0},
                       {"reference":rf3,"table_id":"t_a","starts_at_local":T}]},
        token=ada, idem=key())
    check_status("C-MV-9", st, 422, b)
    # cancelled booking in batch -> 409 reservation_cancelled, nothing changes
    r4 = book(ada, "t_a", utc_local(200*60))[1]; rf4 = r4.get("reference")
    call("POST", f"/reservations/{rf4}/cancel", token=ada)
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":rf4,"party_size":2},{"reference":rf1,"party_size":4}]},
        token=ada, idem=key())
    check_status("C-MV-8", st, 409, b, code="reservation_cancelled")
    st, hd, b, _ = call("GET", f"/reservations/{rf1}", token=ada)
    expect("C-MV-8b", (j(b) or {}).get("party_size") == 2, "atomic: later move not applied")
    # cutoff precedes other errors for that booking: seed near-cutoff booking
    fx = fixture_base()
    fx["reservations"] = [{"id":"rs_n","reference":"NEARX1","user_id":"u_ada",
        "restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(60),"party_size":2}]
    reset(fx)
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":"NEARX1","party_size":0}]}, token=ada, idem=key())
    check_status("C-MV-10", st, 409, b, code="cutoff_passed")
    # successful batch replay: 200 original even after later amendment
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    r5 = book(ada, "t_a", utc_local(160*60))[1]; r6 = book(ada, "t_b", utc_local(160*60))[1]
    km = key("mv")
    mvbody = {"moves":[{"reference":r5.get("reference"),"party_size":3},
                       {"reference":r6.get("reference"),"party_size":1}]}
    st, hd, b, _ = call("POST", "/reservation-moves", body=mvbody, token=ada, idem=km)
    check_status("C-MV-6", st, 201, b); orig_mv = j(b)
    # then amend r5 again directly
    call("PATCH", f"/reservations/{r5.get('reference')}", body={"party_size":4}, token=ada)
    st, hd, b, _ = call("POST", "/reservation-moves", body=mvbody, token=ada, idem=km)
    check_status("C-MV-14", st, 200, b)
    expect("C-MV-14b", j(b) == orig_mv, "batch replay returns original response")
    # no-op move retains values + unknown fields ignored
    st, hd, b, _ = call("POST", "/reservation-moves",
        body={"moves":[{"reference":r6.get("reference"),"bogus_field":1}]}, token=ada, idem=key())
    check_status("C-MV-15", st, 201, b)
    x = ((j(b) or {}).get("reservations") or [{}])[0]
    expect("C-MV-15b", x.get("party_size") == 1 and x.get("table_id") == "t_b", "no-op retains")

# ---------------- DST ----------------

def sec_dst():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    # Berlin spring forward 2026-03-29 (sun): 02:00/02:30 nonexistent
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_berlin&date=2026-03-29&party_size=2")
    slots = [s["starts_at_local"] for s in (j(b) or {}).get("slots", [])]
    expect("C-DST-1", "2026-03-29T02:00" not in slots and "2026-03-29T02:30" not in slots and
           "2026-03-29T01:30" in slots and "2026-03-29T03:00" in slots, f"gap slots {slots}")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id":"r_berlin","table_id":"tb_1","starts_at_local":"2026-03-29T02:30","party_size":2})
    check_status("C-DST-1b", st, 422, b, code="invalid_local_time")
    # Berlin fall back 2026-10-25 (sun): 02:30 once, resolves +02:00
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_berlin&date=2026-10-25&party_size=2")
    slots = [s["starts_at_local"] for s in (j(b) or {}).get("slots", [])]
    expect("C-DST-2", slots.count("2026-10-25T02:30") == 1 and slots.count("2026-10-25T02:00") == 1,
           f"fold listing {slots}")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id":"r_berlin","table_id":"tb_1","starts_at_local":"2026-10-25T02:30","party_size":2})
    check_status("C-DST-2b", st, 201, b)
    expect("C-DST-2c", (j(b) or {}).get("starts_at") == "2026-10-25T02:30:00+02:00",
           f"first occurrence {j(b) and j(b).get('starts_at')}")
    # absolute duration: book 01:30 on fold night -> ends_at reads 02:00 local (+01:00)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id":"r_berlin","table_id":"tb_1","starts_at_local":"2026-10-25T01:30","party_size":2})
    check_status("C-DST-3", st, 201, b)
    expect("C-DST-3b", (j(b) or {}).get("ends_at") == "2026-10-25T02:00:00+01:00",
           f"ends_at {j(b) and j(b).get('ends_at')}")
    # NYC spring forward 2026-03-08 (sun)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id":"r_nyc","table_id":"tn_1","starts_at_local":"2026-03-08T02:30","party_size":2})
    check_status("C-DST-4", st, 422, b, code="invalid_local_time")
    # NYC fall back 2026-11-01 (sun): 01:30 -> -04:00 (EDT, first occurrence)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id":"r_nyc","table_id":"tn_1","starts_at_local":"2026-11-01T01:30","party_size":2})
    check_status("C-DST-5", st, 201, b)
    expect("C-DST-5b", (j(b) or {}).get("starts_at") == "2026-11-01T01:30:00-04:00",
           f"ny fold {j(b) and j(b).get('starts_at')}")
    # winter offset sanity (sun hours only on r_berlin; 2027-01-03 is a Sunday)
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_berlin&date=2027-01-03&party_size=2")
    if (j(b) or {}).get("slots"):
        expect("C-DST-6", (j(b) or {})["slots"][0]["starts_at"].endswith("+01:00"), "winter +01:00")

# ---------------- export / import ----------------

def sec_export_import():
    reset()
    _, bd = login("ada@example.com", "correct horse"); ada = bd["token"]
    # build state: signup, booking with key, a FAILED key, a successful moves batch
    st, bd2 = signup("caro@example.com", "password9", "Caro"); caro = bd2.get("token")
    kx = key("xp")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=kx,
        body={"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(200*60),"party_size":2})
    orig_res = j(b); ref = orig_res.get("reference")
    kf = key("xfail")
    call("POST", "/reservations", token=ada, idem=kf,
         body={"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":"bad","party_size":0})
    kmv = key("xmv")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=kmv,
        body={"moves":[{"reference":ref,"party_size":3}]})
    orig_mv = j(b)
    # C-XP-1 export shape
    st, hd, b, _ = call("GET", "/_test/export")
    check_status("C-XP-1", st, 200, b)
    ex1 = j(b); raw1 = b
    expect("C-XP-1b", isinstance(ex1, dict) and ex1.get("track") == "tablekeeper" and
           ex1.get("format_version") == 1 and isinstance(ex1.get("state"), dict),
           f"export keys {sorted(ex1 or {})}")
    # no plaintext password in export
    expect("C-XP-7", b"correct horse" not in raw1 and b"password9" not in raw1,
           "export free of plaintext passwords")
    # mutate state after export (snapshot test: later writes must not alter export)
    signup("dave@example.com", "password9", "Dave")
    call("POST", "/reservations", token=ada, idem=key(),
         body={"restaurant_id":"r_ops","table_id":"t_b","starts_at_local":utc_local(220*60),"party_size":2})
    st, hd, b2, _ = call("GET", "/_test/export")
    expect("C-XP-6", j(b2) != ex1 or b"dave" in b2.lower(), "second export reflects new state")
    # import the earlier snapshot
    st, hd, b, _ = call("POST", "/_test/import", raw=raw1)
    check_status("C-XP-2", st, 204, b)
    # state restored: dave gone, token still valid, replay returns original
    st, hd, b, _ = call("POST", "/auth/login", body={"email":"dave@example.com","password":"password9"})
    check_status("C-XP-5a", st, 401, b, code="unauthenticated")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    check_status("C-XP-5b", st, 200, b)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=kx,
        body={"restaurant_id":"r_ops","table_id":"t_a","starts_at_local":utc_local(200*60),"party_size":2})
    check_status("C-XP-5c", st, 200, b)
    expect("C-XP-5d", j(b) == orig_res, "idempotent receipt survives import")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=kmv,
        body={"moves":[{"reference":ref,"party_size":3}]})
    check_status("C-XP-5f", st, 200, b)
    expect("C-XP-5f2", j(b) == orig_mv, "moves receipt survives import")
    # previously-failed key still free after import
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=kf,
        body={"restaurant_id":"r_ops","table_id":"t_b","starts_at_local":utc_local(240*60),"party_size":2})
    check_status("C-XP-5e", st, 201, b)
    # repeat import restores identically (no duplication)
    st, hd, b, _ = call("POST", "/_test/import", raw=raw1)
    check_status("C-XP-3", st, 204, b)
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    lst = (j(b) or {}).get("reservations", [])
    expect("C-XP-3b", len(lst) == 1 and lst[0].get("reference") == ref,
           f"no duplication n={len(lst)}")
    # invalid imports leave state untouched
    for raw_inv, want in [(b"{oops", 400),
                          (b'{"track":"other","format_version":1,"state":{}}', 422),
                          (b'{"track":"tablekeeper","format_version":2,"state":{}}', 422),
                          (b'{"track":"tablekeeper","format_version":1}', 422),
                          (b'{"track":"tablekeeper","format_version":1,"state":"x"}', 422)]:
        st, hd, b, _ = call("POST", "/_test/import", raw=raw_inv)
        check_status("C-XP-4", st, want, b)
        st2, hd, b2, _ = call("GET", "/reservations", token=ada)
        expect("C-XP-4b", st2 == 200 and len((j(b2) or {}).get("reservations", [])) == 1,
               "state unchanged after invalid import")
    # reset clears imported state
    call("POST", "/_test/reset", body=fixture_base())
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    check_status("C-XP-8", st, 401, b)
    _, bd = login("ada@example.com", "correct horse")
    st, hd, b, _ = call("GET", "/reservations", token=bd["token"])
    expect("C-XP-8b", (j(b) or {}).get("reservations") == [], "imported reservations cleared by reset")

def sec_perf():
    reset()
    worst = 0.0
    for _ in range(20):
        st, hd, b, dt = call("GET", "/health")
        worst = max(worst, dt)
    expect("C-PERF-1", worst < 5.0, f"worst health latency {worst:.3f}s")

SECTIONS = [sec_runtime, sec_auth, sec_errors, sec_api, sec_availability,
            sec_booking, sec_booking_errors, sec_list_cancel_patch, sec_cutoff,
            sec_idem, sec_concurrency, sec_moves, sec_dst, sec_export_import, sec_perf]

def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--only", default=None, help="substring filter on section name")
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")
    t0 = time.monotonic()
    for s in SECTIONS:
        if args.only and args.only not in s.__name__:
            continue
        try:
            s()
        except Exception as e:
            expect(s.__name__, False, f"check raised {e!r}")
    fails = [r for r in RESULTS if not r[1]]
    print(f"\n== {len(RESULTS)} checks, {len(fails)} FAIL, {len(FIVE_XX)} 5xx/conn-errors, "
          f"{time.monotonic()-t0:.1f}s ==")
    for cid, ok, d in fails:
        print("FAIL", cid, "-", d)
    for cid, st in FIVE_XX:
        print("5XX", cid, st)
    sys.exit(1 if fails or FIVE_XX else 0)

if __name__ == "__main__":
    main()
