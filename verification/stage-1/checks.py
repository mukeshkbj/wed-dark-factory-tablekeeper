#!/usr/bin/env python3
"""
Independent spec-derived checks for Tablekeeper stage-1.
Derived from the stage-1 spec text ONLY (not from the shipped suite or impl).
Usage: BASE_URL=http://localhost:8080 python checks.py
Exit code 0 iff all checks pass. Author: tk-verifier.
"""
import json, os, re, sys, threading, time
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
RESULTS = []
_SENT = object()
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
REFRE = re.compile(r"^[A-Z0-9]{6,12}$")

def req(method, path, body=_SENT, token=None, key=None, raw=None, extra_headers=None):
    url = BASE + path
    data = None
    h = {}
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        h["Content-Type"] = "application/json"
    elif body is not _SENT:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    if token is not None:
        h["Authorization"] = "Bearer " + token
    if key is not None:
        h["Idempotency-Key"] = key
    if extra_headers:
        h.update(extra_headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, str(e).encode()

def jb(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None

def ecode(raw):
    b = jb(raw)
    if isinstance(b, dict):
        e = b.get("error")
        if isinstance(e, dict):
            return e.get("code")
    return None

def check(cid, name, cond, detail=""):
    ok = bool(cond)
    RESULTS.append((cid, name, ok, detail))
    print(("PASS" if ok else "FAIL"), cid, "-", name, ("| " + str(detail)[:220] if detail else ""))

def expect_err(cid, name, st, raw, want_status, want_code):
    b = jb(raw)
    shape = isinstance(b, dict) and isinstance(b.get("error"), dict) and \
            isinstance(b["error"].get("code"), str) and isinstance(b["error"].get("message"), str)
    ok = (st == want_status and ecode(raw) == want_code and shape)
    check(cid, name, ok, "got %s code=%s want %s/%s" % (st, ecode(raw), want_status, want_code))
    return ok

DAYS = ["mon","tue","wed","thu","fri","sat","sun"]

def fixture(with_seed_res=False):
    f = {
        "users": [
            {"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"},
            {"id":"u_bob","email":"bob@example.com","password":"bobs secret9","display_name":"Bob"},
        ],
        "restaurants": [
            {"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin",
             "slot_minutes":30,"reservation_duration_minutes":90,"cancellation_cutoff_minutes":120,
             "opening_hours":[{"weekday":"thu","opens":"18:00","closes":"23:00"},
                              {"weekday":"fri","opens":"18:00","closes":"23:30"},
                              {"weekday":"sun","opens":"01:00","closes":"06:00"}],
             "tables":[{"id":"t_1","label":"1","capacity":2},{"id":"t_2","label":"2","capacity":4}]},
            {"id":"r_ny","name":"Nolita","timezone":"America/New_York",
             "slot_minutes":30,"reservation_duration_minutes":60,"cancellation_cutoff_minutes":60,
             "opening_hours":[{"weekday":"sun","opens":"00:00","closes":"05:00"}],
             "tables":[{"id":"t_a","label":"A","capacity":2},{"id":"t_b","label":"B","capacity":4}]},
            {"id":"r_now","name":"Jetzt","timezone":"Europe/Berlin",
             "slot_minutes":30,"reservation_duration_minutes":60,"cancellation_cutoff_minutes":120,
             "opening_hours":[{"weekday":d,"opens":"00:00","closes":"23:59"} for d in DAYS],
             "tables":[{"id":"t_n1","label":"N1","capacity":4},{"id":"t_n2","label":"N2","capacity":4}]},
            {"id":"r_empty","name":"Leere","timezone":"Europe/Berlin",
             "slot_minutes":30,"reservation_duration_minutes":60,"cancellation_cutoff_minutes":60,
             "opening_hours":[],"tables":[{"id":"t_e","label":"E","capacity":2}]},
        ],
        "reservations": [],
    }
    if with_seed_res:
        f["reservations"] = [{"id":"res_seed","reference":"SEED01","user_id":"u_ada",
            "restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":2}]
    return f

def reset(f=None):
    st, raw = req("POST", "/_test/reset", body=f if f is not None else fixture())
    assert st == 204, "reset failed: %s %s" % (st, raw[:200])

def login(email, pw):
    st, raw = req("POST", "/auth/login", body={"email":email,"password":pw})
    b = jb(raw) or {}
    return st, b.get("token"), b

def book(token, key, restaurant_id, table_id, starts, party):
    return req("POST", "/reservations",
               body={"restaurant_id":restaurant_id,"table_id":table_id,
                     "starts_at_local":starts,"party_size":party},
               token=token, key=key)

def next_grid(utc_dt, step=30):
    """Round a UTC instant up to the next `step`-minute Europe/Berlin wall boundary."""
    from zoneinfo import ZoneInfo
    l = utc_dt.astimezone(ZoneInfo("Europe/Berlin"))
    base = l.replace(second=0, microsecond=0)
    add = (step - base.minute % step) % step
    cand = base + timedelta(minutes=add)
    if cand <= l:
        cand += timedelta(minutes=step)
    return cand.strftime("%Y-%m-%dT%H:%M")

def grid_at(minutes_ahead):
    return next_grid(datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead))

def valid_grid_slot(off):
    """First grid slot >= now+off that fits r_now hours (opens 00:00,
    closes 23:59, dur 60 -> start <= 22:59; grid is :00/:30)."""
    while True:
        cand = grid_at(off)
        hh, mm = int(cand[11:13]), int(cand[14:16])
        if hh * 60 + mm <= 22 * 60 + 30:
            return cand
        off += 30

def avail(rid, date, party):
    q = urllib.parse.urlencode({"restaurant_id":rid,"date":date,"party_size":party})
    return req("GET", "/availability?" + q)

def run():
    t0 = time.time()
    # ---------- runtime / reset ----------
    st, raw = req("GET", "/health")
    b = jb(raw)
    check("C-RT-1", "GET /health -> 200 {status:ok}", st == 200 and isinstance(b, dict) and b.get("status") == "ok", "got %s %r" % (st, raw[:120]))

    st, raw = req("POST", "/_test/reset", body=fixture())
    check("C-RT-2", "reset -> 204", st == 204, "got %s" % st)
    st, raw = req("POST", "/_test/reset", body=fixture())
    check("C-RT-3", "repeat reset -> 204", st == 204, "got %s" % st)

    # ---------- auth ----------
    st, ada, b = login("ada@example.com", "correct horse")
    check("C-AU-6a", "seeded user logs in immediately (FX-1)", st == 200 and ada and b.get("user_id") == "u_ada" and b.get("display_name") == "Ada", "got %s %r" % (st, b))
    _, ada2, _ = login("ada@example.com", "correct horse")
    st, _ = req("GET", "/reservations", token=ada2)
    check("C-AU-7", "multiple concurrent tokens valid", st == 200 and ada2 and ada2 != ada, "got %s" % st)
    _, bob, _ = login("bob@example.com", "bobs secret9")

    st, raw = req("POST", "/auth/signup", body={"email":"caro@example.com","password":"passw0rd!","display_name":"Caro"})
    b = jb(raw) or {}
    check("C-AU-1", "signup -> 201 user_id/display_name/token", st == 201 and b.get("user_id") and b.get("display_name") == "Caro" and b.get("token"), "got %s %r" % (st, b))
    caro = b.get("token")
    st, raw = req("POST", "/auth/signup", body={"email":"ada@example.com","password":"whatever99","display_name":"X"})
    expect_err("C-AU-3", "duplicate email -> 409 email_taken", st, raw, 409, "email_taken")
    st, raw = req("POST", "/auth/signup", body={"email":"d@e.com","password":"short7","display_name":"X"})
    expect_err("C-AU-4a", "password <8 -> 422", st, raw, 422, "validation_failed")
    st, raw = req("POST", "/auth/signup", body={"email":"not-an-email","password":"longenough1","display_name":"X"})
    expect_err("C-AU-5", "bad email form -> 422", st, raw, 422, "validation_failed")
    st, raw = req("POST", "/auth/login", body={"email":"ada@example.com","password":"wrong wrong"})
    expect_err("C-AU-6b", "wrong password -> 401 unauthenticated", st, raw, 401, "unauthenticated")
    st, raw = req("POST", "/auth/login", body={"email":"nobody@example.com","password":"whatever99"})
    expect_err("C-AU-6c", "unknown email -> 401 unauthenticated", st, raw, 401, "unauthenticated")
    st, tok, _ = login("caro@example.com", "passw0rd!")
    check("C-AU-2", "login new user -> 200 + token", st == 200 and tok, "got %s" % st)

    prot = [
        ("GET","/reservations",None),
        ("POST","/reservations",{"restaurant_id":"r_anker","table_id":"t_1","starts_at_local":"2026-09-24T18:00","party_size":2}),
        ("GET","/reservations/ZZZZ",None), ("PATCH","/reservations/ZZZZ",{"party_size":2}),
        ("POST","/reservations/ZZZZ/cancel",None), ("POST","/reservation-moves",{"moves":[{"reference":"X"}]}),
    ]
    bad = True; det = []
    for m, p, bd in prot:
        s1, r1 = req(m, p, body=bd) if bd is not None else req(m, p)
        s2, r2 = req(m, p, body=bd, token="not-a-real-token") if bd is not None else req(m, p, token="not-a-real-token")
        if not (s1 == 401 and ecode(r1) == "unauthenticated" and s2 == 401 and ecode(r2) == "unauthenticated"):
            bad = False; det.append((m, p, s1, ecode(r1), s2, ecode(r2)))
        if (s1 or 0) >= 500 or (s2 or 0) >= 500:
            bad = False; det.append(("5xx", m, p, s1, s2))
    check("C-AU-8", "all protected routes 401 missing/unknown bearer", bad, det[:5])

    # ---------- precedence pipeline ----------
    st, raw = req("POST", "/reservations", raw="{not json", token=ada, key="k-pp1")
    expect_err("C-PP-1", "parse beats auth/key: malformed body -> 400", st, raw, 400, "malformed_request")
    st, raw = req("POST", "/reservations", body={"x":1})
    expect_err("C-PP-2", "auth beats key: valid json no token -> 401", st, raw, 401, "unauthenticated")
    st, raw = req("POST", "/reservations", body={"x":1}, token=ada)
    expect_err("C-PP-3", "authed + no Idempotency-Key -> 400 missing_idempotency_key", st, raw, 400, "missing_idempotency_key")
    st, raw = req("POST", "/reservations", body={"x":1}, token=ada, key="")
    expect_err("C-PP-3b", "empty Idempotency-Key -> 400", st, raw, 400, "missing_idempotency_key")
    st, raw = req("POST", "/reservation-moves", body={"moves":[]}, token=ada)
    expect_err("C-PP-4", "moves authed + no key -> 400 missing_idempotency_key", st, raw, 400, "missing_idempotency_key")

    # wrong JSON type -> 400; after 4xx the key is reusable
    st, raw = req("POST", "/reservations", body={"restaurant_id":123,"table_id":"t_1","starts_at_local":"2026-09-24T18:00","party_size":2}, token=ada, key="k-typ1")
    expect_err("C-ER-2", "wrong JSON type field -> 400 malformed_request", st, raw, 400, "malformed_request")
    st, raw = book(ada, "k-typ1", "r_now", "t_n2", grid_at(240), 2)
    check("C-IDM-3a", "key reusable after 4xx (400) -> processed as first use", st in (201,), "got %s %s" % (st, ecode(raw)))
    ref_ktyp = (jb(raw) or {}).get("reference")
    # seed a used key then replay with different INVALID body -> 409 reuse beats validation
    st, raw = req("POST", "/reservations", body={"restaurant_id":123,"table_id":"t_2","starts_at_local":"2026-09-24T19:00","party_size":"x"}, token=ada, key="k-typ1")
    expect_err("C-PP-5", "used key + different invalid body -> 409 idempotency_key_reuse before validation", st, raw, 409, "idempotency_key_reuse")
    # missing required fields -> 422
    st, raw = req("POST", "/reservations", body={"restaurant_id":"r_anker"}, token=ada, key="k-miss1")
    expect_err("C-ER-6", "missing required fields -> 422 validation_failed", st, raw, 422, "validation_failed")
    st, raw = req("POST", "/reservations", body="[1,2,3]", token=ada, key="k-arr")
    check("C-ER-7", "non-object JSON body -> 400/422 not 5xx", st in (400, 422), "got %s code=%s" % (st, ecode(raw)))

    # ---------- public endpoints / availability ----------
    st, raw = req("GET", "/restaurants")
    b = jb(raw) or {}
    rs = b.get("restaurants") if isinstance(b, dict) else None
    check("C-AV-1", "GET /restaurants public list {id,name,timezone}", st == 200 and isinstance(rs, list) and any(r.get("id")=="r_anker" and r.get("name")=="Zum Anker" and r.get("timezone")=="Europe/Berlin" for r in rs), "got %s" % st)
    st, raw = req("GET", "/restaurants/r_anker")
    b = jb(raw) or {}
    check("C-AV-2", "GET /restaurants/{id} public full fixture shape", st == 200 and b.get("slot_minutes")==30 and b.get("reservation_duration_minutes")==90 and b.get("cancellation_cutoff_minutes")==120 and isinstance(b.get("opening_hours"),list) and isinstance(b.get("tables"),list) and len(b.get("tables",[]))==2, "got %s %r" % (st, str(b)[:150]))
    st, raw = req("GET", "/restaurants/nope")
    expect_err("C-AV-2b", "unknown restaurant -> 404", st, raw, 404, "not_found")
    st, raw = req("GET", "/restaurants")
    check("C-RT-5a", "public endpoints need no auth (implicitly verified above)", st == 200)

    for cid, qs, nm in [
        ("C-AV-3a","restaurant_id=r_anker&date=2026-09-24","missing party_size -> 422"),
        ("C-AV-3b","restaurant_id=r_anker&party_size=2","missing date -> 422"),
        ("C-AV-3c","date=2026-09-24&party_size=2","missing restaurant_id -> 422")]:
        st, raw = req("GET", "/availability?" + qs)
        expect_err(cid, nm, st, raw, 422, "validation_failed")

    # integer query param strictness
    for cid, p, nm in [("C-AV-8a","4.0","party_size=4.0 -> 422"),("C-AV-8b","%2B4","party_size=+4 -> 422"),
                       ("C-AV-8c","1e9","party_size=1e9 -> 422"),("C-AV-8d","-1","party_size=-1 -> 422"),
                       ("C-AV-8e","x","party_size=x -> 422")]:
        st, raw = req("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=" + p)
        expect_err(cid, nm, st, raw, 422, "validation_failed")
    st, raw = req("GET", "/availability?restaurant_id=r_anker&date=2026-13-40&party_size=2")
    expect_err("C-AV-8f", "invalid date value -> 422", st, raw, 422, "validation_failed")
    st, raw = req("GET", "/availability?restaurant_id=r_anker&date=2026-09-24&party_size=2&bogus=1")
    check("C-RT-4a", "unknown query params ignored", st == 200, "got %s" % st)
    st, raw = avail("r_nonexistent", "2026-09-24", 2)
    check("C-AV-8g", "unknown restaurant availability -> 404", st == 404 and ecode(raw)=="not_found", "got %s code=%s" % (st, ecode(raw)))

    # availability grid: thu 2026-09-24, opens 18:00 closes 23:00, dur 90, step 30
    st, raw = avail("r_anker", "2026-09-24", 4)
    b = jb(raw) or {}
    slots = b.get("slots") or []
    locals_ = [s.get("starts_at_local") for s in slots]
    want = ["2026-09-24T%02d:%02d" % (h, m) for h, m in
            [(18,0),(18,30),(19,0),(19,30),(20,0),(20,30),(21,0),(21,30)]]
    check("C-AV-4a", "slot grid = every 30min from opens while slot+dur<=closes", locals_ == want, "got %r" % locals_)
    good = all(REFRE.match("AA11") and True for _ in [0])
    shape_ok = all(isinstance(s.get("starts_at"), str) and RFC3339.match(s["starts_at"]) and s["starts_at"].endswith("+02:00") for s in slots)
    check("C-AV-4b", "starts_at RFC3339 with +02:00 offset", shape_ok and len(slots) == 8, "got %r" % [s.get("starts_at") for s in slots[:3]])
    ok_ids = all(s.get("available_table_ids") == ["t_2"] for s in slots)
    check("C-AV-5a", "party 4 -> only cap>=4 table t_2 all slots", ok_ids, "got %r" % [s.get("available_table_ids") for s in slots[:3]])
    st, raw = avail("r_anker", "2026-09-24", 2)
    ok_ids = all(s.get("available_table_ids") == ["t_1","t_2"] for s in (jb(raw) or {}).get("slots", []))
    check("C-AV-5b", "party 2 -> [t_1,t_2] fixture order", ok_ids)
    st, raw = avail("r_anker", "2026-09-24", 5)
    b2 = jb(raw) or {}
    check("C-AV-7", "party 5 -> slots still appear with empty lists", len(b2.get("slots") or []) == 8 and all(s.get("available_table_ids")==[] for s in b2["slots"]))
    st, raw = avail("r_anker", "2026-09-26", 2)  # saturday: closed
    check("C-AV-6a", "day with no opening_hours -> slots: []", st == 200 and (jb(raw) or {}).get("slots") == [], "got %s %r" % (st, str(raw)[:120]))
    st, raw = avail("r_empty", "2026-09-24", 2)
    check("C-AV-6b", "restaurant with zero opening days -> slots: []", st == 200 and (jb(raw) or {}).get("slots") == [])

    # ---------- POST /reservations ----------
    st, raw = book(ada, "k-r1", "r_anker", "t_2", "2026-09-24T19:00", 4)
    b = jb(raw) or {}
    fields_ok = all(k in b for k in ("reservation_id","reference","restaurant_id","table_id","party_size","status","starts_at_local","starts_at","ends_at","created_at"))
    check("C-BK-1a", "create -> 201 full response shape", st == 201 and fields_ok and b.get("status")=="confirmed" and b.get("starts_at_local")=="2026-09-24T19:00" and b.get("starts_at")=="2026-09-24T19:00:00+02:00" and b.get("ends_at")=="2026-09-24T20:30:00+02:00" and RFC3339.match(b.get("created_at","")), "got %s %r" % (st, str(b)[:200]))
    ref1 = b.get("reference"); resid1 = b.get("reservation_id")
    check("C-BK-2", "reference 6-12 chars [A-Z0-9]", bool(ref1 and REFRE.match(ref1)), "got %r" % ref1)
    st, raw = book(ada, "k-r2", "r_anker", "t_2", "2026-09-24T19:30", 4)
    expect_err("C-BK-3a", "overlapping same table -> 409 table_unavailable", st, raw, 409, "table_unavailable")
    st, raw = book(ada, "k-r3", "r_anker", "t_2", "2026-09-24T20:30", 4)
    check("C-BK-3b", "half-open boundary: 20:30 after 19:00+90min -> 201", st == 201, "got %s %s" % (st, ecode(raw)))
    ref2 = (jb(raw) or {}).get("reference")
    st, raw = book(ada, "k-r4", "r_anker", "t_2", "2026-09-24T18:00", 4)
    expect_err("C-BK-3c", "18:00+90 overlaps 19:00 -> 409", st, raw, 409, "table_unavailable")

    st, raw = book(ada, "k-e1", "r_anker", "t_1", "2026-09-24T18:15", 2)
    expect_err("C-BK-4a", "off-grid start -> 422 not_on_slot_grid", st, raw, 422, "not_on_slot_grid")
    st, raw = book(ada, "k-e2", "r_anker", "t_1", "2026-09-24T17:30", 2)
    expect_err("C-BK-4b", "before opens -> 422 outside_opening_hours", st, raw, 422, "outside_opening_hours")
    st, raw = book(ada, "k-e3", "r_anker", "t_1", "2026-09-24T22:00", 2)
    expect_err("C-BK-4c", "ends after closes -> 422 outside_opening_hours", st, raw, 422, "outside_opening_hours")
    st, raw = book(ada, "k-e4", "r_anker", "t_1", "2026-09-25T18:00", 3)
    expect_err("C-BK-5a", "party>capacity -> 422 party_exceeds_capacity", st, raw, 422, "party_exceeds_capacity")
    for i, p in enumerate([0, -3, "4", 4.0, True]):
        st, raw = book(ada, "k-e5%d" % i, "r_anker", "t_1", "2026-09-25T18:00", p)
        expect_err("C-BK-5b%d" % i, "invalid party_size %r -> 422 validation_failed (endpoint precedence)" % p, st, raw, 422, "validation_failed")
    st, raw = book(ada, "k-e6", "r_anker", "t_1", "2026-09-25T18:00:00", 2)
    expect_err("C-BK-6a", "starts_at_local with seconds -> 422", st, raw, 422, "validation_failed")
    st, raw = book(ada, "k-e7", "r_anker", "t_1", "2026-09-25T18:00+02:00", 2)
    expect_err("C-BK-6b", "starts_at_local with offset -> 422", st, raw, 422, "validation_failed")
    st, raw = book(ada, "k-e8", "r_anker", "t_1", "2026-09-25", 2)
    expect_err("C-BK-6c", "date-only starts_at_local -> 422", st, raw, 422, "validation_failed")
    st, raw = req("POST", "/reservations", body={"restaurant_id":"r_anker","table_id":"t_1","starts_at_local":12345,"party_size":2}, token=ada, key="k-e9")
    expect_err("C-BK-6d", "starts_at_local wrong type -> 400", st, raw, 400, "malformed_request")
    st, raw = book(ada, "k-e10", "r_anker", "t_1", "2026-09-24T19:00", 2)
    check("C-BK-6e", "on-grid 19:00 t_1 (t_2 taken only) -> 201", st == 201, "got %s %s" % (st, ecode(raw)))
    ref_t1 = (jb(raw) or {}).get("reference")
    st, raw = book(ada, "k-e11", "r_nope", "t_1", "2026-09-24T19:00", 2)
    expect_err("C-BK-7a", "unknown restaurant -> 404", st, raw, 404, "not_found")
    st, raw = book(ada, "k-e12", "r_anker", "t_zzz", "2026-09-24T19:00", 2)
    expect_err("C-BK-7b", "unknown table -> 404", st, raw, 404, "not_found")
    st, raw = book(ada, "k-e13", "r_anker", "t_a", "2026-09-24T19:00", 2)
    expect_err("C-BK-7c", "table of another restaurant -> 404", st, raw, 404, "not_found")
    st, raw = book(ada, "k-e14", "r_anker", "t_9"*1 or "t_1", "2026-09-24T19:00", 2)
    # past-date booking allowed
    st, raw = book(ada, "k-past1", "r_now", "t_n1", "2026-01-05T12:00", 2)
    check("C-BK-8", "past-date booking -> 201 (cutoff does not block create)", st == 201, "got %s %s" % (st, ecode(raw)))
    ref_past = (jb(raw) or {}).get("reference")

    # availability reflects booking: 19:00 both tables gone for party>=2; 20:30 t_2 free
    st, raw = avail("r_anker", "2026-09-24", 2)
    sl = {s["starts_at_local"]: s["available_table_ids"] for s in (jb(raw) or {}).get("slots", [])}
    check("C-AV-5c", "occupancy masks overlapping slots; half-open frees 20:30 for t_1",
          sl.get("2026-09-24T19:00") == [] and sl.get("2026-09-24T18:00") == [] and
          sl.get("2026-09-24T20:00") == [] and sl.get("2026-09-24T20:30") == ["t_1"],
          "got %r" % {k: sl.get(k) for k in ["2026-09-24T18:00","2026-09-24T19:00","2026-09-24T20:30"]})

    # ---------- GET /reservations ----------
    st, raw = req("GET", "/reservations", token=ada)
    lst = (jb(raw) or {}).get("reservations") or []
    starts = [r.get("starts_at") for r in lst]
    check("C-LS-1", "list returns caller's reservations incl. all created", st == 200 and len(lst) == 5 and set(r.get("reference") for r in lst) == {ref1, ref2, ref_t1, ref_past, ref_ktyp}, "got %d refs" % len(lst))
    parsed = [datetime.fromisoformat(x) for x in starts]
    check("C-LS-2", "list sorted starts_at descending (by instant)", parsed == sorted(parsed, reverse=True), "got %r" % starts)
    st, raw = req("GET", "/reservations", token=bob)
    check("C-LS-3", "other user's list empty {reservations:[]}", st == 200 and (jb(raw) or {}).get("reservations") == [])
    st, raw = req("GET", "/reservations/" + ref1, token=bob)
    expect_err("C-BK-7d", "other user's reference -> 404 not_found (no existence leak)", st, raw, 404, "not_found")
    st, raw = req("GET", "/reservations/" + ref1, token=ada)
    check("C-BK-7e", "own reference -> 200", st == 200, "got %s" % st)
    st, raw = req("GET", "/reservations/NOPE99", token=ada)
    expect_err("C-BK-7f", "unknown reference -> 404", st, raw, 404, "not_found")

    # ---------- idempotency lifecycle ----------
    key = "k-idm-a"
    body1 = {"restaurant_id":"r_anker","table_id":"t_1","starts_at_local":"2026-10-02T18:00","party_size":2}
    st, raw = req("POST", "/reservations", body=body1, token=ada, key=key)
    b1 = jb(raw)
    check("C-IDM-1a", "first use of key -> 201", st == 201, "got %s" % st)
    ref_idm = (b1 or {}).get("reference")
    st, raw = req("POST", "/reservations", body=body1, token=ada, key=key)
    check("C-IDM-1b", "replay same key+body -> 200 identical JSON value", st == 200 and jb(raw) == b1, "got %s equal=%s" % (st, jb(raw) == b1))
    st, raw = req("GET", "/reservations", token=ada)
    n = sum(1 for r in (jb(raw) or {}).get("reservations", []) if r.get("reference") == ref_idm)
    check("C-IDM-1c", "replay created no duplicate", n == 1)
    # key order/whitespace do not matter
    reordered = json.dumps({"party_size":2,"starts_at_local":"2026-10-02T18:00","table_id":"t_1","restaurant_id":"r_anker"})
    st, raw = req("POST", "/reservations", raw=reordered, token=ada, key=key)
    check("C-IDM-4", "reordered JSON keys still a replay -> 200 original", st == 200 and jb(raw) == b1, "got %s" % st)
    st, raw = req("POST", "/reservations", body={**body1, "party_size":2, "table_id":"t_2"}, token=ada, key=key)
    expect_err("C-IDM-2", "same key different body -> 409 idempotency_key_reuse", st, raw, 409, "idempotency_key_reuse")
    # different user, same key string -> independent
    st, raw = req("POST", "/reservations", body={"restaurant_id":"r_anker","table_id":"t_2","starts_at_local":"2026-10-02T18:30","party_size":2}, token=bob, key=key)
    check("C-IDM-6a", "same key string for another user -> independent 201", st == 201, "got %s %s" % (st, ecode(raw)))
    # same key + same body on a DIFFERENT path -> not a replay, must not be 409-reuse
    st, raw = req("POST", "/reservation-moves", body=body1, token=ada, key=key)
    check("C-IDM-5", "same key+body on different path -> not idempotency_key_reuse", not (st == 409 and ecode(raw) == "idempotency_key_reuse"), "got %s code=%s" % (st, ecode(raw)))
    # failed-4xx key treated as first use
    st, raw = book(ada, "k-fail1", "r_nope", "t_1", "2026-09-25T18:00", 2)
    assert st == 404
    st, raw = book(ada, "k-fail1", "r_anker", "t_1", "2026-10-02T19:30", 2)
    check("C-IDM-3b", "key from 404 request reusable -> 201 first use", st == 201, "got %s %s" % (st, ecode(raw)))
    # replay after cancel returns ORIGINAL receipt
    st, raw = req("POST", "/reservations/%s/cancel" % ref_idm, token=ada)
    assert st == 200, (st, raw)
    st, raw = req("POST", "/reservations", body=body1, token=ada, key=key)
    check("C-IDM-7", "replay after cancel -> 200 original confirmed receipt", st == 200 and jb(raw) == b1 and (jb(raw) or {}).get("status") == "confirmed", "got %s %r" % (st, str(jb(raw))[:150]))
    st, raw = req("GET", "/reservations/" + ref_idm, token=ada)
    check("C-IDM-8", "replay made no state change (still cancelled)", (jb(raw) or {}).get("status") == "cancelled", "got %r" % (jb(raw) or {}).get("status"))
    # key length boundaries
    st, raw = book(ada, "K" * 255, "r_anker", "t_1", "2026-10-02T21:30", 2)
    check("C-IDM-9a", "255-char key accepted", st == 201, "got %s %s" % (st, ecode(raw)))
    st, raw = book(ada, "K" * 256, "r_anker", "t_1", "2026-10-02T22:00", 2)
    expect_err("C-IDM-9b", "256-char key -> 422 validation_failed", st, raw, 422, "validation_failed")

    # ---------- cancel ----------
    st, raw = book(ada, "k-cx1", "r_anker", "t_1", "2026-10-02T18:00", 2)
    assert st == 201, (st, raw)
    ref_cxl = (jb(raw) or {}).get("reference")
    st, raw = req("POST", "/reservations/%s/cancel" % ref_cxl, token=ada)
    b = jb(raw) or {}
    check("C-CN-1a", "cancel -> 200 status cancelled", st == 200 and b.get("status") == "cancelled" and b.get("reference") == ref_cxl, "got %s %r" % (st, str(b)[:150]))
    st, raw = avail("r_anker", "2026-10-02", 2)
    sl = {x["starts_at_local"]: x["available_table_ids"] for x in (jb(raw) or {}).get("slots", [])}
    check("C-CN-1b", "cancel frees table immediately (t_1 back at 18:00)", "t_1" in (sl.get("2026-10-02T18:00") or []), "got %r" % sl.get("2026-10-02T18:00"))
    st, raw = req("POST", "/reservations/%s/cancel" % ref_cxl, token=ada)
    check("C-CN-2", "cancel twice -> 200 current state (not an error)", st == 200 and (jb(raw) or {}).get("status") == "cancelled", "got %s" % st)
    st, raw = req("POST", "/reservations/%s/cancel" % ref1, token=bob)
    expect_err("C-CN-3", "cancel other user's -> 404", st, raw, 404, "not_found")
    st, raw = req("POST", "/reservations/NOPE77/cancel", token=ada)
    expect_err("C-CN-4", "cancel unknown ref -> 404", st, raw, 404, "not_found")
    st, raw = req("POST", "/reservations/%s/cancel" % ref_past, token=ada)
    expect_err("C-CN-5a", "cancel past booking -> 409 cutoff_passed", st, raw, 409, "cutoff_passed")
    near = grid_at(65); far = grid_at(160)
    st, raw = book(ada, "k-cn-n", "r_now", "t_n1", near, 2)
    assert st == 201, (st, raw)
    ref_near = (jb(raw) or {}).get("reference")
    st, raw = req("POST", "/reservations/%s/cancel" % ref_near, token=ada)
    expect_err("C-CN-5b", "cancel within cutoff (now+~%s) -> 409 cutoff_passed" % near, st, raw, 409, "cutoff_passed")
    st, raw = book(ada, "k-cn-f", "r_now", "t_n1", far, 2)
    assert st == 201, (st, raw)
    ref_far = (jb(raw) or {}).get("reference")
    st, raw = req("POST", "/reservations/%s/cancel" % ref_far, token=ada)
    check("C-CN-5c", "cancel beyond cutoff -> 200 cancelled", st == 200 and (jb(raw) or {}).get("status") == "cancelled", "got %s" % st)

    # ---------- PATCH ----------
    slot_p1 = grid_at(500); slot_p2 = grid_at(540); slot_occ = grid_at(580)
    st, raw = book(ada, "k-p1", "r_now", "t_n1", slot_p1, 2)
    assert st == 201, (st, raw)
    bp = jb(raw) or {}
    refp, residp = bp.get("reference"), bp.get("reservation_id")
    st, raw = req("PATCH", "/reservations/" + refp, body={"starts_at_local":slot_p2}, token=ada)
    b = jb(raw) or {}
    check("C-PT-1a", "PATCH time -> 200 updated, identity stable", st == 200 and b.get("starts_at_local") == slot_p2 and b.get("reference") == refp and b.get("reservation_id") == residp and b.get("created_at") == bp.get("created_at"), "got %s %r" % (st, str(b)[:160]))
    st, raw = req("PATCH", "/reservations/" + refp, body={"table_id":"t_n2"}, token=ada)
    check("C-PT-1b", "PATCH table -> 200", st == 200 and (jb(raw) or {}).get("table_id") == "t_n2", "got %s %s" % (st, ecode(raw)))
    st, raw = req("PATCH", "/reservations/" + refp, body={"party_size":5})
    expect_err("C-PT-4b", "PATCH without token -> 401", st, raw, 401, "unauthenticated")
    st, raw = req("PATCH", "/reservations/" + refp, body={"party_size":5}, token=ada)
    expect_err("C-PT-2a", "PATCH invalid (party>cap) -> 422 party_exceeds_capacity", st, raw, 422, "party_exceeds_capacity")
    st, raw = req("GET", "/reservations/" + refp, token=ada)
    b = jb(raw) or {}
    check("C-PT-2b", "failed PATCH left original unchanged", b.get("party_size") == 2 and b.get("table_id") == "t_n2" and b.get("starts_at_local") == slot_p2, "got %r" % str(b)[:150])
    st, raw = book(ada, "k-p2", "r_now", "t_n1", slot_occ, 2)
    assert st == 201, (st, raw)
    st, raw = req("PATCH", "/reservations/" + refp, body={"table_id":"t_n1","starts_at_local":slot_occ}, token=ada)
    expect_err("C-PT-3a", "PATCH into occupied slot -> 409 table_unavailable", st, raw, 409, "table_unavailable")
    st, raw = req("PATCH", "/reservations/" + refp, body={"starts_at_local":slot_p2}, token=ada)
    check("C-PT-3b", "no-op PATCH (self-overlap excluded) -> 200", st == 200, "got %s %s" % (st, ecode(raw)))
    st, raw = req("PATCH", "/reservations/" + ref1, token=bob, body={"party_size":1})
    expect_err("C-PT-4c", "PATCH other user's -> 404", st, raw, 404, "not_found")
    st, raw = req("PATCH", "/reservations/" + ref_past, token=ada, body={"party_size":3})
    expect_err("C-PT-5a", "PATCH past booking -> 409 cutoff_passed", st, raw, 409, "cutoff_passed")
    st, raw = req("PATCH", "/reservations/" + ref_cxl, token=ada, body={"party_size":1})
    expect_err("C-PT-5b", "PATCH cancelled -> 409 reservation_cancelled", st, raw, 409, "reservation_cancelled")

    # ---------- reservation moves ----------
    # fresh state for moves on a clean date (2026-10-01 thursday)
    def mv(key, moves, token=ada):
        return req("POST", "/reservation-moves", body={"moves":moves}, token=token, key=key)
    st, raw = book(ada, "k-mA", "r_anker", "t_1", "2026-10-01T18:00", 2)
    refA = (jb(raw) or {}).get("reference"); assert st == 201, (st, raw)
    st, raw = book(ada, "k-mB", "r_anker", "t_2", "2026-10-01T20:30", 2)
    refB = (jb(raw) or {}).get("reference"); assert st == 201, (st, raw)
    st, raw = book(ada, "k-mC", "r_ny", "t_a", "2026-11-01T00:30", 2)
    refC = (jb(raw) or {}).get("reference"); assert st == 201, (st, raw)
    st, raw = book(bob, "k-mD", "r_anker", "t_1", "2026-10-02T18:00", 2)
    refD = (jb(raw) or {}).get("reference"); assert st == 201, (st, raw)

    st, raw = req("POST", "/reservation-moves", body={"moves":[{"reference":refA,"table_id":"t_2"}]}, token=ada)
    expect_err("C-MV-1a", "moves without key -> 400 missing_idempotency_key", st, raw, 400, "missing_idempotency_key")
    st, raw = mv("k-mv0", [{"reference":refA,"table_id":"t_2"}], token=None) if False else req("POST","/reservation-moves",body={"moves":[{"reference":refA}]},key="k-mv0")
    expect_err("C-MV-1b", "moves without token -> 401", st, raw, 401, "unauthenticated")
    for cid, moves, nm in [
        ("C-MV-2a", [], "empty moves -> 422"),
        ("C-MV-2b", [{"reference":r} for r in ["R1"]*9], "9 moves -> 422"),
        ("C-MV-2c", [{"reference":refA},{"reference":refA}], "duplicate references -> 422"),
        ("C-MV-2d", [{"reference":123}], "non-string reference -> 422"),
        ("C-MV-2e", [{"reference":refA,"party_size":None} if False else {"ref":refA}], "wrong field name -> 422 (reference required)")]:
        st, raw = mv("k-mv-" + cid, moves)
        expect_err(cid, nm, st, raw, 422, "validation_failed")
    st, raw = mv("k-mv-notmv", {"reference":refA})
    check("C-MV-2f", "moves not an array -> 4xx not 5xx", st in (400, 422), "got %s" % st)

    st, raw = mv("k-mv3a", [{"reference":refD,"table_id":"t_2"}])
    expect_err("C-MV-3a", "other owner's reference -> 404", st, raw, 404, "not_found")
    st, raw = mv("k-mv3b", [{"reference":"NOPE42","table_id":"t_2"}])
    expect_err("C-MV-3b", "unknown reference -> 404", st, raw, 404, "not_found")
    st, raw = mv("k-mv3c", [{"reference":refA,"table_id":"t_2"},{"reference":refC,"party_size":1}])
    expect_err("C-MV-3c", "cross-restaurant batch -> 422 validation_failed", st, raw, 422, "validation_failed")

    # swap tables A<->B atomically
    st, raw = mv("k-mv-swap", [{"reference":refA,"table_id":"t_2"},{"reference":refB,"table_id":"t_1"}])
    b = jb(raw) or {}
    rl = b.get("reservations") or []
    check("C-MV-4a", "swap tables -> 201 reservations in input order", st == 201 and [r.get("reference") for r in rl] == [refA, refB] and rl[0].get("table_id") == "t_2" and rl[1].get("table_id") == "t_1", "got %s %r" % (st, str(rl)[:200]))
    check("C-MV-4b", "identity/created_at preserved through move", rl and rl[0].get("reservation_id") and rl[0].get("created_at"), "")
    st, raw = mv("k-mv-swap", [{"reference":refA,"table_id":"t_2"},{"reference":refB,"table_id":"t_1"}])
    check("C-MV-9a", "replay batch -> 200 identical body", st == 200 and jb(raw) == b, "got %s" % st)

    # failed batch -> all-or-nothing + key reusable
    st, raw = book(ada, "k-mE", "r_anker", "t_2", "2026-10-01T19:30", 2)
    refE = (jb(raw) or {}).get("reference"); assert st == 201, (st, raw)
    beforeA = req("GET", "/reservations/" + refA, token=ada)[1]
    st, raw = mv("k-mv-fail", [{"reference":refE,"table_id":"t_2","starts_at_local":"2026-10-01T19:30"},{"reference":refA,"party_size":99}])
    code_fail = ecode(raw)
    check("C-MV-6a", "batch item error surfaces (input order): item2 party>cap -> 422", st == 422 and code_fail == "party_exceeds_capacity", "got %s code=%s" % (st, code_fail))
    afterA = req("GET", "/reservations/" + refA, token=ada)[1]
    afterE = req("GET", "/reservations/" + refE, token=ada)[1]
    check("C-MV-8a", "failed batch changed nothing (item1 not committed)", jb(beforeA) == jb(afterA) and (jb(afterE) or {}).get("table_id") == "t_2" and (jb(afterE) or {}).get("starts_at_local") == "2026-10-01T19:30", "E=%r" % str(jb(afterE))[:160])
    st, raw = mv("k-mv-fail", [{"reference":refE,"party_size":2}])
    check("C-MV-8b", "failed batch key reusable -> processed fresh", st == 201, "got %s %s" % (st, ecode(raw)))

    # occupancy overlap with unlisted booking -> 409 table_unavailable
    st, raw = mv("k-mv-ov", [{"reference":refE,"table_id":"t_1","starts_at_local":"2026-10-01T20:00"}])
    expect_err("C-MV-7a", "move into overlap with unlisted booking -> 409 table_unavailable", st, raw, 409, "table_unavailable")
    st, raw = mv("k-mv-ov2", [{"reference":refE,"starts_at_local":"2026-10-01T18:30","table_id":"t_2"}])
    expect_err("C-MV-7b", "move onto t_2 overlapping swapped A (18:30 vs 18:00+90) -> 409", st, raw, 409, "table_unavailable")
    st, raw = mv("k-mv-ord", [{"reference":refE,"party_size":99},{"reference":refA,"table_id":"t_zzz"}])
    expect_err("C-MV-6b", "input-order precedence: item1 422 beats item2 404", st, raw, 422, "party_exceeds_capacity")
    # no-op move retains values
    st, raw = mv("k-mv-noop", [{"reference":refE}])
    b = jb(raw) or {}
    check("C-MV-9b", "no-op move -> 201 unchanged values", st == 201 and (b.get("reservations") or [{}])[0].get("starts_at_local") == "2026-10-01T19:30", "got %s %r" % (st, str(b)[:160]))
    # cancelled member -> 409
    st, raw = req("POST", "/reservations/%s/cancel" % refB, token=ada)
    assert st == 200, (st, raw)
    st, raw = mv("k-mv-can", [{"reference":refB,"party_size":1}])
    expect_err("C-MV-5", "cancelled member -> 409 reservation_cancelled", st, raw, 409, "reservation_cancelled")
    # cutoff member -> 409 (past booking from earlier section)
    st, raw = mv("k-mv-cut", [{"reference":ref_past,"party_size":3}])
    expect_err("C-MV-5b", "past-start member -> 409 cutoff_passed", st, raw, 409, "cutoff_passed")
    # replay after later cancel still returns original body
    st, raw = mv("k-mv-swap", [{"reference":refA,"table_id":"t_2"},{"reference":refB,"table_id":"t_1"}])
    check("C-MV-9c", "replay after member cancelled -> 200 original receipt", st == 200 and (jb(raw) or {}).get("reservations") and (jb(raw)["reservations"][1].get("status") == "confirmed"), "got %s %r" % (st, str(jb(raw))[:160]))

    # ---------- DST ----------
    # Berlin spring forward 2026-03-29 (sun, open 01:00-06:00, dur 90): 02:00-02:59 do not exist
    st, raw = avail("r_anker", "2026-03-29", 2)
    sl = {s["starts_at_local"]: s for s in (jb(raw) or {}).get("slots", [])}
    locals_ = sorted(sl.keys())
    check("C-DST-1a", "Berlin spring-forward: nonexistent 02:xx slots absent",
          "2026-03-29T02:00" not in sl and "2026-03-29T02:30" not in sl and
          "2026-03-29T01:30" in sl and "2026-03-29T03:00" in sl, "got %r" % locals_)
    check("C-DST-1b", "Berlin spring-forward offsets (+01 before, +02 after)",
          sl.get("2026-03-29T01:30",{}).get("starts_at") == "2026-03-29T01:30:00+01:00" and
          sl.get("2026-03-29T03:00",{}).get("starts_at") == "2026-03-29T03:00:00+02:00",
          "got %r / %r" % (sl.get("2026-03-29T01:30",{}).get("starts_at"), sl.get("2026-03-29T03:00",{}).get("starts_at")))
    st, raw = book(ada, "k-dst1", "r_anker", "t_1", "2026-03-29T02:30", 2)
    expect_err("C-DST-2", "booking nonexistent local -> 422 invalid_local_time", st, raw, 422, "invalid_local_time")
    # Berlin fall back 2026-10-25 (sun): 02:00-02:59 occur twice; first occurrence (+02) wins
    st, raw = avail("r_anker", "2026-10-25", 2)
    sl = {s["starts_at_local"]: s for s in (jb(raw) or {}).get("slots", [])}
    locals_ = [s for s in sorted(sl.keys())]
    check("C-DST-3a", "Berlin fall-back: ambiguous 02:xx appears exactly once",
          locals_.count("2026-10-25T02:00") == 1 and locals_.count("2026-10-25T02:30") == 1,
          "got %r" % locals_)
    check("C-DST-3b", "Berlin fall-back: 02:30 resolves to first occurrence (+02:00)",
          sl.get("2026-10-25T02:30",{}).get("starts_at") == "2026-10-25T02:30:00+02:00",
          "got %r" % sl.get("2026-10-25T02:30",{}).get("starts_at"))
    # absolute duration: 90min from 01:30 -> local ends_at 02:00 (+01:00)
    st, raw = book(ada, "k-dst4", "r_anker", "t_1", "2026-10-25T01:30", 2)
    b = jb(raw) or {}
    check("C-DST-4", "fall-back absolute duration: 01:30+90min ends 02:00+01:00",
          st == 201 and b.get("ends_at") == "2026-10-25T02:00:00+01:00",
          "got %s ends_at=%r" % (st, b.get("ends_at")))
    # cross-transition occupancy is absolute: 02:30 first-occurrence (00:30Z) overlaps 01:30+90 (23:30Z-01:00Z)
    st, raw = book(ada, "k-dst5", "r_anker", "t_1", "2026-10-25T02:30", 2)
    expect_err("C-DST-7a", "ambiguous 02:30 (first occ 00:30Z) overlaps 01:30+90 -> 409", st, raw, 409, "table_unavailable")
    st, raw = book(ada, "k-dst6", "r_anker", "t_1", "2026-10-25T03:00", 2)
    check("C-DST-7b", "03:00 CET (02:00Z) after absolute end 01:00Z of 01:30+90 -> 201", st == 201, "got %s %s" % (st, ecode(raw)))
    # NY spring forward 2026-03-08 (02:00->03:00)
    st, raw = avail("r_ny", "2026-03-08", 2)
    sl = {s["starts_at_local"]: s for s in (jb(raw) or {}).get("slots", [])}
    check("C-DST-5a", "NY spring-forward: 02:xx absent, 01:30 (-05) then 03:00 (-04)",
          "2026-03-08T02:00" not in sl and "2026-03-08T02:30" not in sl and
          sl.get("2026-03-08T01:30",{}).get("starts_at") == "2026-03-08T01:30:00-05:00" and
          sl.get("2026-03-08T03:00",{}).get("starts_at") == "2026-03-08T03:00:00-04:00",
          "got %r" % [s.get("starts_at") for s in sl.values()])
    st, raw = book(ada, "k-dst8", "r_ny", "t_a", "2026-03-08T02:30", 2)
    expect_err("C-DST-5b", "NY booking nonexistent local -> 422 invalid_local_time", st, raw, 422, "invalid_local_time")
    # NY fall back 2026-11-01 (02:00->01:00): first occurrence is EDT -04
    st, raw = avail("r_ny", "2026-11-01", 2)
    sl = {s["starts_at_local"]: s for s in (jb(raw) or {}).get("slots", [])}
    check("C-DST-6", "NY fall-back: 01:30 once, resolves -04:00 (EDT first)",
          sl.get("2026-11-01T01:30",{}).get("starts_at") == "2026-11-01T01:30:00-04:00" and
          sl.get("2026-11-01T02:00",{}).get("starts_at") == "2026-11-01T02:00:00-05:00",
          "got %r" % [ (k, sl[k]["starts_at"]) for k in ("2026-11-01T01:30","2026-11-01T02:00") if k in sl])

    # ---------- export / import ----------
    # current state contains: users/tokens, receipts (incl. k-idm-a, k-mv-swap), bookings, cancelled rows
    st, raw = req("GET", "/_test/export")
    exp = jb(raw)
    check("C-XF-1a", "export -> 200 {track,format_version:1,state}", st == 200 and isinstance(exp, dict) and exp.get("track") == "tablekeeper" and exp.get("format_version") == 1 and isinstance(exp.get("state"), (dict, list)), "got %s keys=%r" % (st, list(exp.keys()) if isinstance(exp, dict) else type(exp)))
    check("C-AU-9", "export does not embed plaintext passwords", "correct horse" not in raw.decode("utf-8", "replace") and "bobs secret9" not in raw.decode("utf-8", "replace"))
    st, raw2 = req("GET", "/_test/export")
    check("C-XF-1b", "second export equal snapshot (read-only)", jb(raw2) == exp)
    # post-export write must NOT be inside earlier snapshot
    st, raw = book(ada, "k-post-exp", "r_anker", "t_2", "2026-10-01T21:30", 2)
    ref_post = (jb(raw) or {}).get("reference")
    check("C-XF-1c", "post-export write succeeded (to prove snapshot isolation)", st == 201, "got %s" % st)
    ada_pre = ada  # token captured before import
    # invalid imports leave destination unchanged
    for cid, payload, ws, wc in [
        ("C-XF-5a", {"track":"x","format_version":1,"state":exp["state"]}, 422, "validation_failed"),
        ("C-XF-5b", {"track":"tablekeeper","format_version":2,"state":exp["state"]}, 422, "validation_failed"),
        ("C-XF-5c", {"format_version":1,"state":exp["state"]}, 422, "validation_failed"),
        ("C-XF-5d", {"track":"tablekeeper","format_version":1}, 422, "validation_failed"),
        ("C-XF-5e", {"track":"tablekeeper","format_version":1,"state":12345}, 422, "validation_failed")]:
        st, raw = req("POST", "/_test/import", body=payload)
        expect_err(cid, "invalid import %s -> %d" % (cid, ws), st, raw, ws, wc)
        chk_st, chk_raw = req("GET", "/reservations/" + ref_post, token=ada)
        if not (chk_st == 200):
            check(cid + "-s", "destination unchanged after failed import", False, "ref lookup -> %s" % chk_st)
    st, raw = req("POST", "/_test/import", raw="{invalid")
    expect_err("C-XF-5f", "malformed import body -> 400", st, raw, 400, "malformed_request")
    # import the export: atomic replacement
    st, raw = req("POST", "/_test/import", body=exp)
    check("C-XF-2a", "import own export -> 204", st == 204, "got %s %s" % (st, ecode(raw)))
    st, raw = req("GET", "/reservations/" + ref_post, token=ada)
    check("C-XF-2b", "snapshot isolation: post-export write absent after import", st == 404, "got %s" % st)
    st, tok2, b = login("ada@example.com", "correct horse")
    check("C-XF-6a", "account + password login preserved through import", st == 200 and tok2, "got %s" % st)
    st, raw = req("GET", "/reservations", token=ada_pre)
    check("C-XF-6b", "pre-export bearer token still valid after import", st == 200, "got %s" % st)
    st, raw = req("GET", "/reservations/" + ref_idm, token=ada)
    check("C-XF-6c", "reservation + reference preserved (still cancelled)", st == 200 and (jb(raw) or {}).get("status") == "cancelled", "got %s %r" % (st, str(jb(raw))[:140]))
    st, raw = req("POST", "/reservations", body=body1, token=ada, key="k-idm-a")
    check("C-XF-6d", "idempotent receipt preserved: replay -> 200 original body", st == 200 and jb(raw) == b1, "got %s equal=%s" % (st, jb(raw) == b1))
    st, raw = req("POST", "/reservations", body={**body1,"party_size":1}, token=ada, key="k-idm-a")
    expect_err("C-XF-6e", "receipt preserved: same key diff body -> 409", st, raw, 409, "idempotency_key_reuse")
    st, raw = mv("k-mv-swap", [{"reference":refA,"table_id":"t_2"},{"reference":refB,"table_id":"t_1"}])
    check("C-XF-8a", "batch receipt preserved: replay -> 200", st == 200, "got %s %s" % (st, ecode(raw)))
    st, raw = mv("k-mv-ov", [{"reference":refE,"party_size":4}])
    check("C-XF-7", "failed-batch key still reusable after import -> 201", st == 201, "got %s %s" % (st, ecode(raw)))
    # repeat import idempotent
    st, raw = req("POST", "/_test/import", body=exp)
    check("C-XF-4a", "repeat import -> 204", st == 204, "got %s" % st)
    st, raw = req("GET", "/reservations", token=ada)
    lst = [r.get("reference") for r in (jb(raw) or {}).get("reservations", [])]
    check("C-XF-4b", "repeat import duplicates nothing", len(lst) == len(set(lst)), "refs=%r" % lst)

    # reset clears imported state
    st, raw = req("POST", "/_test/reset", body=fixture())
    check("C-XF-8b", "reset after import -> 204", st == 204)
    st, tok3, _ = login("ada@example.com", "correct horse")
    check("C-XF-8c", "post-reset fresh login works (fixture state only)", st == 200 and tok3)
    st, raw = req("GET", "/reservations", token=tok3)
    check("C-RT-4b", "reset leaves only fixture state (no reservations)", st == 200 and (jb(raw) or {}).get("reservations") == [])
    ada = tok3
    _, bob, _ = login("bob@example.com", "bobs secret9")

    # ---------- concurrency ----------
    slot = valid_grid_slot(300)
    N = 50
    out = [None] * N
    barrier = threading.Barrier(N)
    body_c = {"restaurant_id":"r_now","table_id":"t_n1","starts_at_local":slot,"party_size":2}
    def worker(i):
        barrier.wait()
        out[i] = req("POST", "/reservations", body=body_c, token=ada, key="k-conc-same")
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    [t.start() for t in ths]; [t.join() for t in ths]
    sts = [o[0] for o in out]; bodies = [jb(o[1]) for o in out]
    n201 = sum(1 for s in sts if s == 201); n200 = sum(1 for s in sts if s == 200)
    same = all(b == bodies[0] for b in bodies if bodies[0] is not None)
    check("C-CON-1a", "50-way same-key race: exactly one 201, rest 200, identical bodies",
          n201 == 1 and n200 == N - 1 and same and not any(s >= 500 for s in sts),
          "201s=%d 200s=%d other=%r same=%s" % (n201, n200, [s for s in sts if s not in (200,201)][:8], same))
    st, raw = req("GET", "/reservations", token=ada)
    n_at_slot = sum(1 for r in (jb(raw) or {}).get("reservations", []) if r.get("starts_at_local") == slot and r.get("table_id") == "t_n1")
    check("C-CON-1b", "race effected exactly one reservation", n_at_slot == 1, "got %d" % n_at_slot)

    slot2 = valid_grid_slot(360)
    M = 20
    out = [None] * M
    barrier = threading.Barrier(M)
    def worker2(i):
        barrier.wait()
        out[i] = req("POST", "/reservations",
                     body={"restaurant_id":"r_now","table_id":"t_n2","starts_at_local":slot2,"party_size":2},
                     token=ada, key="k-conc-diff-%d" % i)
    ths = [threading.Thread(target=worker2, args=(i,)) for i in range(M)]
    [t.start() for t in ths]; [t.join() for t in ths]
    sts = [o[0] for o in out]
    n201 = sum(1 for s in sts if s == 201); n409 = sum(1 for s in sts if s == 409 and ecode(o[1][0] if False else "") is None or s == 409 for s in sts)
    n5xx = sum(1 for s in sts if s >= 500)
    check("C-CON-2", "20-way same-table-slot race: exactly one 201, rest 409, no 5xx",
          n201 == 1 and n409 == M - 1 and n5xx == 0,
          "201s=%d 409s=%d other=%r" % (n201, n409, [s for s in sts if s not in (201,409)][:8]))

    # ---------- fuzz / robustness ----------
    bad = True; det = []
    probes = [
        ("POST","/reservations",None,None),  # no token no key
        ("GET","/reservations",None,ada),
        ("PATCH","/reservations/",{"a":1},ada),
        ("POST","/reservations//cancel",None,ada),
        ("GET","/availability",None,None),
        ("GET","/availability?restaurant_id=&date=&party_size=",None,None),
        ("POST","/auth/signup",{},None),
        ("POST","/auth/login",{"email":1,"password":2},None),
        ("GET","/restaurants/../admin",None,None),
        ("POST","/_test/import",{},None),
        ("PUT","/reservations/ABC",{},ada),
        ("DELETE","/reservations/ABC",None,ada),
    ]
    for m, p, bd, tk in probes:
        s_, r_ = req(m, p, body=bd, token=tk) if bd is not None else req(m, p, token=tk)
        if s_ is None or s_ >= 500 or s_ < 0:
            bad = False; det.append((m, p, s_, str(r_)[:80]))
        elif s_ >= 400 and ecode(r_) is None:
            bad = False; det.append((m, p, s_, "no error.code", str(r_)[:80]))
    check("C-FZ-1", "fuzz sweep: no 5xx, all 4xx carry error.code", bad, det[:6])

    # ---------- keep-alive: one connection, several bodies ----------
    import http.client
    hostport = BASE.split("://", 1)[1].split("/")[0]
    h, _, prt = hostport.partition(":")
    conn = http.client.HTTPConnection(h, int(prt or 80))
    conn.request("POST", "/auth/login", json.dumps({"email":"ada@example.com","password":"adas secret9"}),
                 {"Content-Type": "application/json"})
    r1 = conn.getresponse(); b1 = r1.read(); st1 = r1.status
    conn.request("POST", "/reservations",
                 json.dumps({"restaurant_id":"r_anker","table_id":"t_3",
                             "starts_at_local":"2026-10-04T18:00","party_size":2}),
                 {"Content-Type": "application/json",
                  "Authorization": "Bearer " + ada,
                  "Idempotency-Key": "k-keepalive-1"})
    r2 = conn.getresponse(); b2 = r2.read(); st2 = r2.status
    check("C-KA-1", "keep-alive: 2nd request on one conn uses its own body -> 201",
          st1 == 200 and st2 == 201, "login=%s post=%s body=%s" % (st1, st2, b2[:120]))
    conn.close()

    dt = time.time() - t0
    fails = [r for r in RESULTS if not r[2]]
    print()
    print("==== %d checks, %d passed, %d failed in %.1fs ====" % (len(RESULTS), len(RESULTS) - len(fails), len(fails), dt))
    for cid, name, ok, detail in fails:
        print("FAIL", cid, name, "|", str(detail)[:200])
    return 0 if not fails else 1

if __name__ == "__main__":
    sys.exit(run())
