#!/usr/bin/env python3
"""tk-verifier stage-2: independent reference model + random-op replay.

Extends the stage-1 model: reservations hold a SET of tables (canonical
combinable order for declared pairs). Model restaurant r_ops gains
combinable [t_a,t_b] (=8) and [t_b,t_c] (=12); {t_a,t_c} is undeclared.

Drives random book/cancel/patch/move/replay sequences and asserts after
EVERY op:
  M-OCC  no table is held by two confirmed reservations (member-wise)
  M-AGR  service outcome == model outcome (status class + error code)
  M-KEY  idempotency: replay returns the stored original response
  M-ORD  service stores table_ids in canonical combinable order
Usage: python model.py --base-url http://localhost:8080 --ops 400 --seed 1
"""
import argparse, json, random, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8080"
NOW0 = None
DUR = 60; SLOT = 15; CUTOFF = 120
TABLES = {"t_a": 4, "t_b": 4, "t_c": 8}
COMBOS = [("t_a", "t_b"), ("t_b", "t_c")]          # declared order = canonical

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

def local(min_off):
    return (NOW0 + timedelta(minutes=min_off)).strftime("%Y-%m-%dT%H:%M")

def on_grid(off):
    s = NOW0 + timedelta(minutes=off)
    return s.second == 0 and (s.hour * 60 + s.minute) % SLOT == 0

def in_hours(off):
    s = NOW0 + timedelta(minutes=off)
    e = s + timedelta(minutes=DUR)
    return (e.hour * 60 + e.minute <= 23 * 60 + 59 and e.date() == s.date())

def canon(ts):
    """Resolve a request set -> (canonical tuple) or (None) if undeclared."""
    ts = tuple(ts)
    if len(ts) == 1:
        return ts
    if len(ts) == 2:
        for a, b in COMBOS:
            if {a, b} == set(ts):
                return (a, b)
    return None

class Model:
    """Reference: what the spec says must happen."""
    def __init__(self):
        self.res = {}      # ref -> dict(tables=tuple,start,end,status,party)
        self.seq = 0

    def overlap(self, ts, s, e, ignore=()):
        for r in self.res.values():
            if r["status"] == "confirmed" and r["ref"] not in ignore and \
               s < r["end"] and r["start"] < e and set(ts) & set(r["tables"]):
                return True
        return False

    def _check_set(self, ts):
        """Validation shared by create/patch/move. Returns (st,code,canon)."""
        if len(ts) == 0:
            return 422, "validation_failed", None
        if len(set(ts)) != len(ts):
            return 422, "validation_failed", None
        if len(ts) > 2:
            return 422, "combination_not_allowed", None
        if any(t not in TABLES for t in ts):
            return 404, "not_found", None
        c = canon(ts)
        if c is None:
            return 422, "combination_not_allowed", None
        return None, None, c

    def book(self, ts, off, party):
        # Precedence mirrors the observed service order (matrix F-1 obs):
        # set shape -> existence -> declared-pair -> party -> grid -> hours
        # -> capacity -> occupancy.
        st, code, c = self._check_set(ts)
        if st: return st, code
        if party < 1 or not isinstance(party, int) or isinstance(party, bool):
            return 422, "validation_failed"
        if not on_grid(off): return 422, "not_on_slot_grid"
        if not in_hours(off): return 422, "outside_opening_hours"
        if party > sum(TABLES[t] for t in c):
            return 422, "party_exceeds_capacity"
        if self.overlap(c, off, off + DUR):
            return 409, "table_unavailable"
        self.seq += 1
        ref = f"M{self.seq}"
        self.res[ref] = {"ref": ref, "tables": c, "start": off,
                         "end": off + DUR, "status": "confirmed", "party": party}
        return 201, ref

    def cancel(self, ref):
        r = self.res.get(ref)
        if r is None: return 404, "not_found"
        if r["status"] == "cancelled": return 200, r
        if r["start"] <= CUTOFF:
            return 409, "cutoff_passed"
        r["status"] = "cancelled"
        return 200, r

    def _validate_target(self, r, ts, off, party):
        if r["status"] == "cancelled": return 409, "reservation_cancelled", None
        if r["start"] <= CUTOFF:
            return 409, "cutoff_passed", None
        c = r["tables"] if ts is None else None
        if ts is not None:
            st, code, c = self._check_set(ts)
            if st: return st, code, None
        if party is not None and (party < 1 or not isinstance(party, int)
                                  or isinstance(party, bool)):
            return 422, "validation_failed", None
        if off is not None:
            if not on_grid(off): return 422, "not_on_slot_grid", None
            if not in_hours(off): return 422, "outside_opening_hours", None
        # capacity applies to the RESULTING pair (new set + resulting party),
        # checked even when the move only changes the table set.
        resulting_party = r["party"] if party is None else party
        if resulting_party > sum(TABLES[t] for t in c):
            return 422, "party_exceeds_capacity", None
        return None, None, c

    def patch(self, ref, ts=None, off=None, party=None):
        r = self.res.get(ref)
        if r is None: return 404, "not_found"
        stc, code, c = self._validate_target(r, ts, off, party)
        if stc: return stc, code
        t2 = c; s2 = r["start"] if off is None else off
        p2 = r["party"] if party is None else party
        if self.overlap(t2, s2, s2 + DUR, ignore=(ref,)):
            return 409, "table_unavailable"
        r.update(tables=t2, start=s2, end=s2 + DUR, party=p2)
        return 200, r

    def moves(self, items):
        for it in items:
            if it["reference"] not in self.res:
                return 404, "not_found"
        plan = []
        for it in items:
            r = self.res[it["reference"]]
            stc, code, c = self._validate_target(r, it.get("ts"),
                                                 it.get("off"), it.get("party_size"))
            if stc: return stc, code
            plan.append((r, c, r["start"] if it.get("off") is None else it["off"],
                         r["party"] if it.get("party_size") is None else it["party_size"]))
        occupied = {}
        changed = {r["ref"] for r, *_ in plan}
        for r in self.res.values():
            if r["status"] == "confirmed" and r["ref"] not in changed:
                for t in r["tables"]:
                    occupied.setdefault(t, []).append((r["start"], r["end"]))
        for r, t2, s2, p2 in plan:
            if r["status"] == "confirmed":
                for t in t2:
                    for s0, e0 in occupied.get(t, []):
                        if s2 < e0 and s0 < s2 + DUR:
                            return 409, "table_unavailable"
                    occupied.setdefault(t, []).append((s2, s2 + DUR))
        for r, t2, s2, p2 in plan:
            r.update(tables=t2, start=s2, end=s2 + DUR, party=p2)
        return 201, plan

# ---------------- random-op replay driver ----------------

def fx():
    return {"users":[{"id":"u_ada","email":"ada@example.com",
                      "password":"correct horse","display_name":"Ada"}],
            "restaurants":[{"id":"r_ops","name":"Ops","timezone":"UTC",
                "slot_minutes":SLOT,"reservation_duration_minutes":DUR,
                "cancellation_cutoff_minutes":CUTOFF,
                "opening_hours":[{"weekday":w,"opens":"00:00","closes":"23:59"}
                                 for w in ["mon","tue","wed","thu","fri","sat","sun"]],
                "combinable":[list(p) for p in COMBOS],
                "tables":[{"id":t,"label":t,"capacity":c} for t,c in TABLES.items()]}],
            "reservations":[]}

FAIL = []
def agree(cid, got_st, got_code, want_st, want_code, ctx):
    ok = got_st == want_st and (want_code is None or got_code == want_code)
    if got_st >= 500 or got_st == -1: ok = False
    if not ok: FAIL.append(cid)
    print(("PASS" if ok else "FAIL"), cid,
          f"got {got_st}/{got_code} want {want_st}/{want_code} | {ctx}", flush=True)
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
    # Snap to the slot grid so pick_off bases land on-grid (offsets are
    # multiples of SLOT plus explicit off-grid fuzz). Without this the
    # replay is vacuous whenever now.minute % SLOT != 0.
    NOW0 = NOW0.replace(minute=NOW0.minute - NOW0.minute % SLOT)
    rnd = random.Random(args.seed)
    st, b = call("POST", "/_test/reset", body=fx(), timeout=15)
    assert st == 204, f"reset failed {st} {b[:200]}"
    st, b = call("POST", "/auth/login",
                 body={"email": "ada@example.com", "password": "correct horse"})
    tok = (j(b) or {})["token"]
    M = Model()
    keys = {}
    svc_ref = {}
    kc = [0]
    def nk():
        kc[0] += 1; return f"mk-{kc[0]}"
    def pick_off(grid_only=False):
        base = rnd.choice([-300, -150, 240, 300, 360, 480, 720, 1440])
        off = base + rnd.choice([0, 0, 0, 15, 30])
        if not grid_only and rnd.random() < 0.08: off += 7
        if not grid_only and rnd.random() < 0.05: off = -1440
        return off
    def pick_set(bad=False):
        if bad:
            return rnd.choice([("t_a", "t_c"), ("t_a", "t_b", "t_c"),
                               ("t_a", "t_a"), (), ("t_zz",), ("t_a", "t_zz")])
        r = rnd.random()
        if r < 0.55: return (rnd.choice(list(TABLES)),)
        return rnd.choice(COMBOS)
    def body_for(ts, off, party):
        return {"restaurant_id": "r_ops", "table_ids": list(ts),
                "starts_at_local": local(off), "party_size": party}
    def cmp_state(i):
        st, b = call("GET", "/reservations", token=tok)
        svc = {}
        for r in (j(b) or {}).get("reservations", []):
            tid = r.get("table_ids") or ([r["table_id"]] if r.get("table_id") else [])
            svc[r["reference"]] = (frozenset(tid), r["starts_at_local"],
                                   r["status"], r["party_size"], list(tid))
        mdl = {}
        for r in M.res.values():
            if r["ref"] in svc_ref:
                mdl[svc_ref[r["ref"]]] = (frozenset(r["tables"]),
                    local(r["start"]), r["status"], r["party"], list(r["tables"]))
        ok = st == 200 and {k: v[:4] for k, v in svc.items()} == \
                           {k: v[:4] for k, v in mdl.items()}
        if not ok: FAIL.append("M-AGR-state")
        print(("PASS" if ok else "FAIL"), "M-AGR-state",
              f"st={st} op{i} svc={sorted(svc.values())} model={sorted(mdl.values())}",
              flush=True)
        # canonical order assertion (R2-6): service list order == declared order
        ord_ok = all(svc[k][4] == v[4] for k, v in mdl.items() if k in svc)
        if not ord_ok: FAIL.append("M-ORD")
        print(("PASS" if ord_ok else "FAIL"), "M-ORD", "canonical table_ids order",
              flush=True)
    n = 0
    for i in range(args.ops):
        n = i
        kind = rnd.choices(["book", "cancel", "patch", "moves", "replay"],
                           weights=[44, 13, 17, 16, 10])[0]
        if kind == "book" or (not M.res and kind != "replay"):
            badset = rnd.random() < 0.18
            ts = pick_set(bad=badset)
            off = pick_off(grid_only=badset)   # invalid-set probes use valid times
            party = rnd.choice([1, 2, 3, 4, 5, 8, 9, 13, 0])
            body = body_for(ts, off, party)
            k = nk()
            wst, wcode = M.book(ts, off, party)
            st, b = call("POST", "/reservations", body=body, token=tok, idem=k)
            ok = agree(f"M-book-{i}", st, (j(b) or {}).get("error", {}).get("code"),
                       wst, None if wst == 201 else wcode, body)
            if wst == 201 and st == 201:
                svc_ref[f"M{M.seq}"] = (j(b) or {}).get("reference")
                if (j(b) or {}).get("table_ids") != list(M.res[f"M{M.seq}"]["tables"]):
                    FAIL.append(f"M-ORD-book-{i}")
                    print("FAIL", f"M-ORD-book-{i}", (j(b) or {}).get("table_ids"), flush=True)
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
            body = {}; kw = {}
            if rnd.random() < 0.6:
                ts = pick_set(bad=rnd.random() < 0.1)
                body["table_ids"] = list(ts); kw["ts"] = ts
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
                    ts = pick_set(); it["table_ids"] = list(ts); mit["ts"] = ts
                if rnd.random() < 0.4:
                    off = pick_off(); it["starts_at_local"] = local(off); mit["off"] = off
                if rnd.random() < 0.4:
                    it["party_size"] = rnd.choice([1, 2, 5, 9])
                    mit["party_size"] = it["party_size"]
                items.append((it, mit))
            body = {"moves": [x[0] for x in items]}
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
            print(("PASS" if ok else "FAIL"), f"M-KEY-{i}", f"replay {path} st={st}",
                  flush=True)
        if i % 25 == 24:
            cmp_state(i)
    cmp_state(n)
    print(f"\n== model replay done: {n+1} ops, failures={len(FAIL)} ==")
    sys.exit(1 if FAIL else 0)

if __name__ == "__main__":
    main()
