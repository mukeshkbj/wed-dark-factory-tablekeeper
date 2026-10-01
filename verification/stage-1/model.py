#!/usr/bin/env python3
"""tk-verifier stage-1: independent reference model + random-op replay.

Drives random book/cancel/patch/move/replay sequences against the live service
on the model restaurant (UTC, all-week 00:00-23:59, slot 15, dur 60, cutoff 120)
and asserts, after EVERY op:
  M-OCC  no table is held by two confirmed reservations (model & service agree)
  M-AGR  service outcome == model outcome (status class + error code)
  M-KEY  idempotency: replay returns the stored original response
Usage: python model.py --base-url http://localhost:8080 --ops 400 --seed 1
"""
import argparse, json, random, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8080"
NOW0 = None  # frozen at run start; ops are scheduled relative to it
DUR = 60; SLOT = 15; CUTOFF = 120; TABLES = {"t_a": 4, "t_b": 4, "t_c": 8}

def call(method, path, body=None, token=None, idem=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    if token: h["Authorization"] = "Bearer " + token
    if idem: h["Idempotency-Key"] = idem
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def j(b):
    try: return json.loads(b)
    except Exception: return None

def local(min_off):  # model-time UTC wall clock string
    return (NOW0 + timedelta(minutes=min_off)).strftime("%Y-%m-%dT%H:%M")

def on_grid(off):
    s = NOW0 + timedelta(minutes=off)
    return s.second == 0 and (s.hour * 60 + s.minute) % SLOT == 0

def in_hours(off):   # r_ops 00:00-23:59 daily; end must be <= 23:59
    s = NOW0 + timedelta(minutes=off)
    e = s + timedelta(minutes=DUR)
    return s.hour * 60 + s.minute >= 0 and (e.hour * 60 + e.minute <= 23 * 60 + 59 and e.date() == s.date())

class Model:
    """Reference: what the spec says must happen."""
    def __init__(self):
        self.res = {}          # ref -> dict(table,start,end,status,party)
        self.keys = {}         # idem key -> (body_json_value, status, resp_json)
        self.seq = 0

    def overlap(self, table, s, e, ignore=()):
        return any(r["status"] == "confirmed" and r["table"] == table and r["ref"] not in ignore
                   and s < r["end"] and r["start"] < e for r in self.res.values())

    def book(self, table, off, party):
        s = off; e = off + DUR
        if party < 1 or not isinstance(party, int) or isinstance(party, bool):
            return 422, "validation_failed"
        if not on_grid(off): return 422, "not_on_slot_grid"
        if not in_hours(off): return 422, "outside_opening_hours"
        if party > TABLES[table]: return 422, "party_exceeds_capacity"
        if self.overlap(table, s, e): return 409, "table_unavailable"
        self.seq += 1
        ref = f"M{self.seq}"
        self.res[ref] = {"ref": ref, "table": table, "start": s, "end": e,
                         "status": "confirmed", "party": party}
        return 201, ref

    def cancel(self, ref):
        r = self.res.get(ref)
        if r is None: return 404, "not_found"
        if r["status"] == "cancelled": return 200, r
        if r["start"] <= CUTOFF:
            return 409, "cutoff_passed"
        r["status"] = "cancelled"
        return 200, r

    def _validate_target(self, r, table, off, party):
        """Amendment validation order per spec: cancelled -> cutoff -> field rules."""
        if r["status"] == "cancelled": return 409, "reservation_cancelled"
        if r["start"] <= CUTOFF:
            return 409, "cutoff_passed"
        if party is not None and (party < 1 or not isinstance(party, int) or isinstance(party, bool)):
            return 422, "validation_failed"
        if off is not None:
            if not on_grid(off): return 422, "not_on_slot_grid"
            if not in_hours(off): return 422, "outside_opening_hours"
        if party is not None and party > TABLES[table if table else r["table"]]:
            return 422, "party_exceeds_capacity"
        return None, None

    def patch(self, ref, table=None, off=None, party=None):
        r = self.res.get(ref)
        if r is None: return 404, "not_found"
        t2 = table or r["table"]; s2 = r["start"] if off is None else off
        p2 = r["party"] if party is None else party
        stc, code = self._validate_target(r, table, off, party)
        if stc: return stc, code
        if self.overlap(t2, s2, s2 + DUR, ignore=(ref,)):
            return 409, "table_unavailable"
        r.update(table=t2, start=s2, end=s2 + DUR, party=p2)
        return 200, r

    def moves(self, items):
        for it in items:
            r = self.res.get(it["reference"])
            if r is None: return 404, "not_found"
        # input order: first failing non-occupancy error (cutoff precedes per booking)
        plan = []
        for it in items:
            r = self.res[it["reference"]]
            t2 = it.get("table_id", r["table"])
            off = it.get("off")
            p2 = it.get("party_size")
            stc, code = self._validate_target(r, it.get("table_id"), off, p2)
            if stc: return stc, code
            plan.append((r, t2, r["start"] if off is None else off,
                         r["party"] if p2 is None else p2))
        occupied = {}   # table -> list[(s,e)] of resulting + unlisted
        changed = {r["ref"] for r, *_ in plan}
        for r in self.res.values():
            if r["status"] == "confirmed" and r["ref"] not in changed:
                occupied.setdefault(r["table"], []).append((r["start"], r["end"]))
        for r, t2, s2, p2 in plan:
            if r["status"] == "confirmed":
                for s0, e0 in occupied.get(t2, []):
                    if s2 < e0 and s0 < s2 + DUR:
                        return 409, "table_unavailable"
                occupied.setdefault(t2, []).append((s2, s2 + DUR))
        for r, t2, s2, p2 in plan:
            r.update(table=t2, start=s2, end=s2 + DUR, party=p2)
        return 201, plan

# ---------------- random-op replay driver ----------------

def fx():
    return {"users":[{"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"}],
            "restaurants":[{"id":"r_ops","name":"Ops","timezone":"UTC","slot_minutes":SLOT,
                "reservation_duration_minutes":DUR,"cancellation_cutoff_minutes":CUTOFF,
                "opening_hours":[{"weekday":w,"opens":"00:00","closes":"23:59"}
                                 for w in ["mon","tue","wed","thu","fri","sat","sun"]],
                "tables":[{"id":t,"label":t,"capacity":c} for t,c in TABLES.items()]}],
            "reservations":[]}

FAIL = []
def agree(cid, got_st, got_code, want_st, want_code, ctx):
    ok = got_st == want_st and (want_code is None or got_code == want_code)
    if got_st >= 500 or got_st == -1: ok = False
    tag = "PASS" if ok else "FAIL"
    if not ok: FAIL.append(cid)
    print(tag, cid, f"got {got_st}/{got_code} want {want_st}/{want_code} | {ctx}", flush=True)
    return ok

def main():
    global BASE, NOW0
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--ops", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")
    NOW0 = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rnd = random.Random(args.seed)
    st, b = call("POST", "/_test/reset", body=fx(), timeout=15)
    assert st == 204, f"reset failed {st} {b[:200]}"
    st, b = call("POST", "/auth/login", body={"email":"ada@example.com","password":"correct horse"})
    tok = (j(b) or {})["token"]
    M = Model()
    keys = {}   # idem key -> (body dict, status, resp json)
    svc_ref = {}  # model ref -> service reference
    kc = [0]
    def nk():
        kc[0] += 1; return f"mk-{kc[0]}"
    def pick_off():
        # minutes offset avoiding the cutoff boundary band (60..180 keeps margin)
        base = rnd.choice([-300, -150, 240, 300, 360, 480, 720, 1440])
        off = base + rnd.choice([0, 0, 0, 15, 30])
        if rnd.random() < 0.08: off += 7      # off-grid probe
        if rnd.random() < 0.05: off = -1440   # deep past
        return off
    def cmp_state(i):
        st, b = call("GET", "/reservations", token=tok)
        svc = {(r["table_id"], r["starts_at_local"], r["status"], r["party_size"])
               for r in (j(b) or {}).get("reservations", [])}
        mdl = {(r["table"], local(r["start"]), r["status"], r["party"])
               for r in M.res.values() if r["ref"] in svc_ref}
        agree("M-AGR-state", st == 200 and svc == mdl, None, 200, None,
              f"op{i} svc={sorted(svc)} model={sorted(mdl)}")
    n = 0
    for i in range(args.ops):
        n = i
        kind = rnd.choices(["book","cancel","patch","moves","replay"],
                           weights=[46, 14, 16, 16, 8])[0]
        if kind == "book" or not M.res and kind != "replay":
            off = pick_off(); tb = rnd.choice(list(TABLES))
            party = rnd.choice([1, 2, 3, 4, 5, 9, 0])
            body = {"restaurant_id":"r_ops","table_id":tb,
                    "starts_at_local":local(off),"party_size":party}
            k = nk()
            wst, wcode = M.book(tb, off, party)
            st, b = call("POST", "/reservations", body=body, token=tok, idem=k)
            ok = agree(f"M-book-{i}", st, (j(b) or {}).get("error", {}).get("code"),
                       wst, None if wst == 201 else wcode, body)
            if wst == 201 and st == 201:
                svc_ref[f"M{M.seq}"] = (j(b) or {}).get("reference")
            if st < 400:
                keys[k] = (body, st, j(b))
        elif kind == "cancel" and M.res:
            mref = rnd.choice(list(M.res)); sref = svc_ref.get(mref, mref)
            wst, w = M.cancel(mref)
            st, b = call("POST", f"/reservations/{sref}/cancel", token=tok)
            agree(f"M-cancel-{i}", st, (j(b) or {}).get("error", {}).get("code"),
                  wst, None if wst == 200 else w, sref)
        elif kind == "patch" and M.res:
            mref = rnd.choice(list(M.res)); sref = svc_ref.get(mref, mref)
            body = {}
            kw = {}
            if rnd.random() < 0.6:
                tb = rnd.choice(list(TABLES)); body["table_id"] = tb; kw["table"] = tb
            if rnd.random() < 0.5:
                off = pick_off(); body["starts_at_local"] = local(off); kw["off"] = off
            if rnd.random() < 0.5:
                p = rnd.choice([1, 2, 3, 5, 9, 0]); body["party_size"] = p; kw["party"] = p
            wst, w = M.patch(mref, **kw)
            st, b = call("PATCH", f"/reservations/{sref}", body=body, token=tok)
            agree(f"M-patch-{i}", st, (j(b) or {}).get("error", {}).get("code"),
                  wst, None if wst == 200 else w, body)
        elif kind == "moves" and M.res:
            items = []
            for mref in rnd.sample(list(M.res), min(len(M.res), rnd.randint(1, 3))):
                it = {"reference": svc_ref.get(mref, mref)}
                mit = {"reference": mref}
                if rnd.random() < 0.7:
                    tb = rnd.choice(list(TABLES)); it["table_id"] = tb; mit["table_id"] = tb
                if rnd.random() < 0.4:
                    off = pick_off(); it["starts_at_local"] = local(off); mit["off"] = off
                if rnd.random() < 0.4:
                    it["party_size"] = rnd.choice([1, 2, 5]); mit["party_size"] = it["party_size"]
                items.append((it, mit))
            body = {"moves":[x[0] for x in items]}
            k = nk()
            wst, w = M.moves([x[1] for x in items])
            st, b = call("POST", "/reservation-moves", body=body, token=tok, idem=k)
            agree(f"M-moves-{i}", st, (j(b) or {}).get("error", {}).get("code"),
                  wst, None if wst == 201 else w, body)
            if st < 400: keys[k] = (body, st, j(b))
        elif kind == "replay" and keys:
            k, (body, ost, oresp) = rnd.choice(list(keys.items()))
            path = "/reservation-moves" if "moves" in body else "/reservations"
            st, b = call("POST", path, body=body, token=tok, idem=k)
            ok = st == 200 and j(b) == oresp
            if not ok: FAIL.append(f"M-KEY-{i}")
            print(("PASS" if ok else "FAIL"), f"M-KEY-{i}", f"replay {path} st={st}", flush=True)
        if i % 25 == 24:
            cmp_state(i)
    cmp_state(n)
    print(f"\n== model replay done: {n+1} ops, failures={len(FAIL)} ==")
    sys.exit(1 if FAIL else 0)

if __name__ == "__main__":
    main()
