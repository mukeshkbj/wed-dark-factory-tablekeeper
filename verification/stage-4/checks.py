#!/usr/bin/env python3
"""tk-verifier stage-4 black-box checks (spec-derived; stdlib only).

Inherits the COMPLETE stage-3 suite verbatim (which inherits stage-2 and
stage-1) and adds stage-4 sections: closure replan preview (RP), plan apply
+ applied closures (RA), series amendments (SA), seating-repair/series
interaction, concurrency, hardened mode.

Spec: tablekeeper/spec/stage-4.md @803560d + coordinator rulings R4-1..R4-24.

Usage:
  python checks.py --base-url http://localhost:8080     full suite (s1..s4)
  python checks.py --base-url ... --inherited-only      stage-1+2+3 regression
  python checks.py --base-url ... --s4-only             stage-4 sections only
  python checks.py --base-url ... --hardened            hardened-instance probes
  python checks.py --base-url ... --only substring      section-name filter
"""
import argparse, importlib.util, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

_HERE = pathlib.Path(__file__).resolve().parent

def _load_s3():
    p = _HERE.parent / "stage-3" / "checks.py"
    spec = importlib.util.spec_from_file_location("tk_s3_checks", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

s3 = _load_s3()
s2 = s3.s2
s1 = s2.s1
call = s1.call; j = s1.j; expect = s1.expect; note = s1.note
check_status = s1.check_status; err_code = s1.err_code
key = s1.key; utc_local = s1.utc_local; login = s1.login; signup = s1.signup
WEEKDAYS = s1.WEEKDAYS
fixture_p3 = s3.fixture_p3; reset3 = s3.reset3
mgr = s3.mgr; nonmgr = s3.nonmgr
pol = s3.pol; publish = s3.publish; list_policies = s3.list_policies
book = s3.book; hist = s3.hist; decision = s3.decision
entries_of = s3.entries_of; terms_p0_ops = s3.terms_p0_ops
avail = s2.avail; slot_at = s2.slot_at
OPS_HOURS = s3.OPS_HOURS

reset4 = reset3   # same fixture discipline: fixture_p3 has managers on all

# ---------------- stage-4 helpers ----------------

def dt_utc(minutes_from_now):
    """Aware UTC datetime snapped to :15, clamped so same-day bookings stay
    inside r_ops' 00:00-23:59 window (latest 60-min start 22:45)."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    dt = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
    if dt.hour >= 23:
        dt = dt.replace(hour=22, minute=45)
    return dt

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def local(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")

def ref_of(rv):
    """Extract .reference from a call/book result. `book`/`call` return
    (st, headers, body, dt); a raw body may also be passed."""
    body = rv[2] if isinstance(rv, tuple) else rv
    return (j(body) or {}).get("reference")

def replan(token, rid, body, idem=None):
    return call("POST", f"/restaurants/{rid}/replans", body=body,
                token=token, idem=idem if idem is not None else key())

def apply_plan(token, rid, plan_id, body=None, idem=None):
    return call("POST", f"/restaurants/{rid}/replans/{plan_id}/apply",
                body={} if body is None else body,
                token=token, idem=idem if idem is not None else key())

def amend_series(token, sid, body, idem=None):
    return call("POST", f"/series/{sid}/amend", body=body,
                token=token, idem=idem if idem is not None else key())

def export_state():
    st, hd, b, _ = call("GET", "/_test/export")
    return st, j(b)

def restaurant_rev_probe(token, rid, when_lo, when_hi):
    """restaurant_revision is exposed via a free replan preview (R4-11:
    preview echoes current revision without incrementing). Cheap probe: a
    preview on an empty interval returns revision unchanged."""
    st, hd, b, _ = replan(token, rid,
                          {"table_id": "t_a",
                           "from": iso(when_lo), "to": iso(when_hi)})
    return st, j(b)

# ================= RP — replan preview: auth + validation =================

def sec_rp_auth():
    reset4()
    ada = mgr(); bob = nonmgr()
    lo = dt_utc(26 * 60); hi = lo + timedelta(hours=2)
    body = {"table_id": "t_a", "from": iso(lo), "to": iso(hi)}
    # RP-1: auth matrix (R4-1: auth/key before resource errors)
    st, hd, b, _ = call("POST", "/restaurants/r_ops/replans", body=body)
    check_status("C4-RP-1a", st, 401, b)
    st, hd, b, _ = call("POST", "/restaurants/r_ops/replans",
                        body=body, token="bogus")
    check_status("C4-RP-1b", st, 401, b)
    st, hd, b, _ = replan(bob, "r_ops", body)
    check_status("C4-RP-1c", st, 403, b)
    st, hd, b, _ = replan(ada, "r_nope", body)
    check_status("C4-RP-1d", st, 404, b)
    st, hd, b, _ = call("POST", "/restaurants/r_nope/replans", body=body)
    check_status("C4-RP-1e", st, 401, b)      # auth wins over 404
    st, hd, b, _ = call("POST", "/restaurants/r_ops/replans",
                        body=body, token=ada)  # no key
    check_status("C4-RP-1f", st, 400, b)
    expect("C4-RP-1g", err_code(b) == "missing_idempotency_key",
           f"no-key code {err_code(b)}")
    # RP-3: unknown + cross-restaurant table
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_zz", "from": iso(lo),
                           "to": iso(hi)})
    check_status("C4-RP-3a", st, 404, b)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "tn_1", "from": iso(lo),
                           "to": iso(hi)})
    check_status("C4-RP-3b", st, 404, b)      # tn_1 lives in r_nyc
    # RP-4: from/to sweep — bad instants all 422
    good = {"table_id": "t_a", "from": iso(lo), "to": iso(hi)}
    cases = [
        ("naive", {"from": lo.strftime("%Y-%m-%dT%H:%M:%S"),
                   "to": iso(hi)}),
        ("naive2", {"from": iso(lo), "to": hi.strftime("%Y-%m-%dT%H:%M")}),
        ("zulu-ok", None),  # filled below (Z suffix must be accepted)
        ("int", {"from": 123, "to": iso(hi)}),
        ("str", {"from": "soon", "to": iso(hi)}),
        ("null", {"from": None, "to": iso(hi)}),
        ("bool", {"from": True, "to": iso(hi)}),
        ("equal", {"from": iso(lo), "to": iso(lo)}),
        ("reversed", {"from": iso(hi), "to": iso(lo)}),
        ("equal-epoch", {"from": iso(lo),
                         "to": lo.strftime("%Y-%m-%dT%H:%M:%S+00:00")}),
        ("missing_from", "__POP__:from"),
        ("missing_to", "__POP__:to"),
        ("missing_table", "__POP__:table_id"),
    ]
    for name, patch in cases:
        req = dict(good)
        if isinstance(patch, str) and patch.startswith("__POP__:"):
            req.pop(patch.split(":", 1)[1], None)
        elif patch is not None:
            req.update(patch)
        else:
            req["from"] = lo.strftime("%Y-%m-%dT%H:%M:%SZ")
        st, hd, b, _ = replan(ada, "r_ops", req)
        if name == "zulu-ok":
            expect(f"C4-RP-4:{name}", st in (201, 409),
                   f"Z-suffix accepted st={st}")
        else:
            check_status(f"C4-RP-4:{name}", st, 422, b)
    # RP-2: unknown fields ignored
    req = dict(good); req["nonsense"] = {"x": 1}
    st, hd, b, _ = replan(ada, "r_ops", req)
    expect("C4-RP-2", st in (201, 409), f"unknown field st={st}")
    if st == 201:
        expect("C4-RP-2b", "nonsense" not in (j(b) or {}),
               "unknown field not echoed")
    reset4()

# ================= RP — considered set, boundaries =================

def sec_rp_considered():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(30 * 60)
    # Layout (60-min bookings; window = [T0, T0+2h) on closing t_a):
    #   r1  t_a@+0   -> must move to t_b (t_b free in hour 1)
    #   r2  t_b@+60  -> considered, stays
    #   r3  t_c@+60  -> considered, stays
    #   canc t_a@+60 -> inside window but cancelled -> excluded
    #   rk  t_a@+120 -> starts AT 'to'   -> excluded (half-open)
    #   r_end t_a@-60 -> ends AT 'from'  -> excluded (half-open)
    def bk(tok, tbl, off, ps=2):
        return book(tok, "r_ops", local(base + timedelta(minutes=off)),
                    party=ps, table=tbl)
    r1 = bk(ada, "t_a", 0)
    r2 = bk(ada, "t_b", 60)
    r3 = bk(bob, "t_c", 60)
    rk = bk(ada, "t_a", 120)          # starts exactly at 'to' -> NOT considered
    r_end = bk(ada, "t_a", -60)       # ends exactly at 'from' -> NOT considered
    canc = bk(ada, "t_a", 60)         # inside window then cancelled -> excluded
    cref = ref_of(canc)
    call("POST", f"/reservations/{cref}/cancel", body={}, token=ada)
    # cross-restaurant: a booking at r_combo same instant must not appear
    st, hd, b, _ = call("POST", "/reservations",
                        body={"restaurant_id": "r_combo", "table_id": "t_a",
                              "starts_at_local": local(base), "party_size": 1},
                        token=bob, idem=key())
    expect("C4-RP-6:setup-xr", st == 201, f"r_combo booking st={st}")
    frm = iso(base); to = iso(base + timedelta(hours=2))
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to})
    check_status("C4-RP-6", st, 201, b)
    pl = j(b) or {}
    refs = [a.get("reference") for a in pl.get("assignments", [])]
    want = {x for x in (ref_of(r1),
                        ref_of(r2),
                        ref_of(r3)) if x}
    # considered = all overlapping confirmed at r_ops: r1, r2, bob's t_c
    expect("C4-RP-6:set", set(refs) == want and len(refs) == len(set(refs)),
           f"assignments {refs} want={want}")
    expect("C4-RP-6:n", len(refs) == 3, f"considered n={len(refs)} {refs}")
    expect("C4-RP-6:order", refs == sorted(refs),
           f"assignments in reference order {refs}")
    # R4-8/9: r1 -> t_b(4) beats t_c(8); unmoved r2/r3 still counted
    a_by = {a["reference"]: a for a in pl.get("assignments", [])}
    expect("C4-RP-6:mv", (a_by.get(ref_of(r1), {})
                          .get("table_ids")) == ["t_b"]
           and a_by.get(ref_of(r2), {})
              .get("changed") is False,
           f"r1 moved to t_b, r2 unmoved {pl.get('assignments')}")
    expect("C4-RP-9b", pl.get("moved_count") == 1
           and pl.get("unused_seats") == 2 + 2 + 6,
           f"moved={pl.get('moved_count')} unused={pl.get('unused_seats')}")
    # boundary bookings absent
    expect("C4-RP-5:to", ref_of(rk) not in refs,
           "booking starting at 'to' not considered")
    expect("C4-RP-5:from", ref_of(r_end) not in refs,
           "booking ending at 'from' not considered")
    expect("C4-RP-5:cancelled", cref not in refs,
           "cancelled overlapping not considered")
    reset4()

# ================= RP — optimization, shape, side effects =================

def sec_rp_plan():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(32 * 60)
    frm = iso(base); to = iso(base + timedelta(hours=2))
    # RP-13/17: single booking p2 on t_b; closing t_b.
    # Options: t_a(4, unused 2) vs t_c(8, unused 6) -> must pick t_a.
    r = book(bob, "r_ops", local(base), party=2, table="t_b")
    ref = ref_of(r)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_b", "from": frm, "to": to})
    check_status("C4-RP-13a", st, 201, b)
    pl = j(b) or {}
    expect("C4-RP-15", set(pl.keys()) >= {"plan_id", "restaurant_revision",
           "closure", "assignments", "moved_count", "unused_seats"},
           f"keys {sorted(pl.keys())}")
    expect("C4-RP-15b", pl.get("closure") ==
           {"table_id": "t_b", "from": frm, "to": to},
           f"closure echoes request {pl.get('closure')}")
    asg = pl.get("assignments") or []
    expect("C4-RP-16", len(asg) == 1 and asg[0].get("reference") == ref
           and set(asg[0].keys()) == {"reference", "table_ids", "changed"},
           f"assignment shape {asg}")
    expect("C4-RP-17", pl.get("moved_count") == 1
           and pl.get("unused_seats") == 2 and asg[0].get("changed") is True
           and asg[0].get("table_ids") == ["t_a"],
           f"moved={pl.get('moved_count')} unused={pl.get('unused_seats')} "
           f"-> {asg[0].get('table_ids')}")
    # RP-14: rank vector — party4 booking on t_b closing; t_a(cap4,rank0)
    # and t_c(cap8,rank2) both leave unused 4 vs 4? no: unused t_a=0 t_c=4
    # -> t_a anyway. Use r_combo where two pairs tie: see note below.
    reset4()
    ada = mgr()
    base = dt_utc(34 * 60)
    frm = iso(base); to = iso(base + timedelta(hours=2))
    # Two bookings: t_a(p2) fixed elsewhere? -> multi-booking moved-count min:
    # close t_a; booking on t_a must move; booking on t_b must NOT move.
    r1 = book(ada, "r_ops", local(base), party=2, table="t_a")
    r2 = book(ada, "r_ops", local(base), party=3, table="t_b")
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to})
    check_status("C4-RP-13b", st, 201, b)
    pl = j(b) or {}
    asg = {a["reference"]: a for a in pl.get("assignments", [])}
    expect("C4-RP-13c", pl.get("moved_count") == 1,
           f"minimal moved {pl.get('moved_count')}")
    ref2 = ref_of(r2)
    expect("C4-RP-13d", asg.get(ref2, {}).get("changed") is False
           and asg.get(ref2, {}).get("table_ids") == ["t_b"],
           f"uninvolved booking unmoved {asg.get(ref2)}")
    ref1 = ref_of(r1)
    expect("C4-RP-13e", asg.get(ref1, {}).get("changed") is True
           and asg.get(ref1, {}).get("table_ids") == ["t_c"],
           f"t_a booking to t_c (t_b held) {asg.get(ref1)}")
    # unused: r1 p2 -> t_c(8): 6 ; r2 p3 -> t_b(4): 1 ; total 7
    expect("C4-RP-9", pl.get("unused_seats") == 7,
           f"unused_seats sums unchanged too, got {pl.get('unused_seats')}")
    reset4()

def sec_rp_limits_effects():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(36 * 60)
    frm = iso(base); to = iso(base + timedelta(hours=2))
    # RP-19: close t_c while a p6 booking sits there -> no_feasible_plan
    r = book(bob, "r_ops", local(base), party=6, table="t_c")
    ref = ref_of(r)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_c", "from": frm, "to": to})
    check_status("C4-RP-19", st, 409, b)
    expect("C4-RP-19b", err_code(b) == "no_feasible_plan",
           f"code {err_code(b)}")
    st, hd, b, _ = call("GET", f"/reservations/{ref}", token=bob)
    rr = j(b) or {}
    expect("C4-RP-19c", rr.get("status") == "confirmed"
           and rr.get("table_ids") == ["t_c"],
           "booking untouched by failed preview")
    st, hd, b, _ = hist(ref, token=bob)
    expect("C4-RP-19d", len(entries_of(b) or []) == 1,
           "no history from failed preview")
    # RP-18: successful preview changes nothing either
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_b", "from": frm, "to": to})
    check_status("C4-RP-18a", st, 201, b)
    pl = j(b) or {}
    rev_before = pl.get("restaurant_revision")
    st2, hd2, b2, _ = replan(ada, "r_ops",
                             {"table_id": "t_a", "from": frm, "to": to})
    rev_after = (j(b2) or {}).get("restaurant_revision")
    expect("C4-RP-18b", rev_after == rev_before,
           f"preview does not bump restaurant_revision {rev_before}->{rev_after}")
    st, hd, b, _ = hist(ref, token=bob)
    expect("C4-RP-18c", len(entries_of(b) or []) == 1
           and (j(b) or {}).get("entries", [{}])[0].get("event") == "created",
           "preview adds no history")
    # availability untouched by pending plan (closure not applied)
    st, hd, b, _ = avail("r_ops", local(base)[:10], 2)
    sl = slot_at(b, local(base))
    opts = [o["table_ids"] for o in
            (sl or {}).get("available_options", [])]
    expect("C4-RP-18d", ["t_b"] in opts,
           f"pending preview leaves availability {opts}")
    # RP-20: preview idempotent replay / key reuse / failed preview frees key
    k1 = key()
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_b", "from": frm, "to": to}, idem=k1)
    st2, hd2, b2, _ = replan(ada, "r_ops",
                             {"table_id": "t_b", "from": frm, "to": to},
                             idem=k1)
    expect("C4-RP-20a", st2 == 200 and j(b2) == j(b),
           f"replay identical st={st2}")
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to}, idem=k1)
    check_status("C4-RP-20b", st, 409, b)
    expect("C4-RP-20c", err_code(b) == "idempotency_key_reuse",
           f"code {err_code(b)}")
    # failed preview frees its key
    kx = key()
    replan(ada, "r_ops", {"table_id": "t_c", "from": frm, "to": to}, idem=kx)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to}, idem=kx)
    expect("C4-RP-20d", st in (201, 409) and err_code(b) != "idempotency_key_reuse",
           f"failed-preview key reusable st={st}")
    # RP-7: planning_limit — 7 considered bookings over a long closure
    reset4()
    ada = mgr()
    for i, tbl in enumerate(("t_a", "t_b", "t_c", "t_a", "t_b", "t_c", "t_a")):
        book(ada, "r_ops", local(base + timedelta(hours=i)), party=1,
             table=tbl)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_c", "from": iso(base - timedelta(hours=1)),
                           "to": iso(base + timedelta(hours=8))})
    check_status("C4-RP-7a", st, 422, b)
    expect("C4-RP-7b", err_code(b) == "planning_limit",
           f"7 considered -> planning_limit, got {err_code(b)}")
    # 6 considered exactly -> supported
    reset4()
    ada = mgr()
    for i, tbl in enumerate(("t_a", "t_b", "t_c", "t_a", "t_b", "t_c")):
        book(ada, "r_ops", local(base + timedelta(hours=i)), party=1,
             table=tbl)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_c", "from": iso(base - timedelta(hours=1)),
                           "to": iso(base + timedelta(hours=8))})
    expect("C4-RP-7c", st in (201, 409),
           f"6 considered supported st={st} code={err_code(b)}")
    # R4-7 limits on restaurant SIZE too: >6 tables or >4 declared pairs
    # are a hard 422 regardless of considered count.
    fx7 = s3.fixture_p3()
    ops7 = next(r for r in fx7["restaurants"] if r["id"] == "r_ops")
    ops7["tables"] = [{"id": f"t_{i}", "label": str(i), "capacity": 4}
                      for i in range(7)]
    reset4(fx7); ada = mgr()
    lo7, hi7 = dt_utc(38 * 60), dt_utc(38 * 60 + 120)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_0", "from": iso(lo7),
                           "to": iso(hi7)})
    expect("C4-RP-7d", st == 422 and err_code(b) == "planning_limit",
           f"7 tables -> planning_limit st={st} {err_code(b)}")
    fxp = s3.fixture_p3()
    cmp5 = next(r for r in fxp["restaurants"] if r["id"] == "r_combo")
    cmp5["tables"] = cmp5["tables"] + [
        {"id": "t_d", "label": "D", "capacity": 4},
        {"id": "t_e", "label": "E", "capacity": 4}]
    cmp5["combinable"] = [["t_a", "t_b"], ["t_b", "t_c"], ["t_a", "t_c"],
                          ["t_a", "t_d"], ["t_b", "t_e"]]
    reset4(fxp); ada = mgr()
    st, hd, b, _ = replan(ada, "r_combo",
                          {"table_id": "t_a", "from": iso(lo7),
                           "to": iso(hi7)})
    expect("C4-RP-7e", st == 422 and err_code(b) == "planning_limit",
           f"5 declared pairs -> planning_limit st={st} {err_code(b)}")

    reset4()


# ================= RA — apply, staleness, closure effects =================

def _mk_plan(ada, rid="r_ops", tbl="t_a", off=0, span=2):
    """Book p2 on tbl at base+off, then preview closure of tbl over 2h.
    Returns (base, ref, plan)."""
    base = dt_utc(38 * 60) + timedelta(minutes=off)
    r = book(ada, rid, local(base), party=2, table=tbl)
    ref = ref_of(r)
    st, hd, b, _ = replan(ada, rid,
                          {"table_id": tbl, "from": iso(base),
                           "to": iso(base + timedelta(hours=span))})
    return base, ref, (j(b) or {}), st

def sec_ra_apply():
    reset4()
    ada = mgr(); bob = nonmgr()
    base, ref, pl, st = _mk_plan(ada)
    expect("C4-RA-0", st == 201 and pl.get("plan_id"),
           f"setup plan st={st} {pl.get('plan_id')}")
    pid = pl.get("plan_id")
    # RA-1: auth matrix on apply
    st, hd, b, _ = call("POST", f"/restaurants/r_ops/replans/{pid}/apply",
                        body={})
    check_status("C4-RA-1a", st, 401, b)
    st, hd, b, _ = apply_plan(bob, "r_ops", pid)
    check_status("C4-RA-1b", st, 403, b)
    st, hd, b, _ = call("POST", f"/restaurants/r_ops/replans/{pid}/apply",
                        body={}, token=ada)
    check_status("C4-RA-1c", st, 400, b)   # missing idem key
    # unknown fields ignored
    st, hd, b, _ = apply_plan(ada, "r_ops", pid, body={"junk": 1})
    expect("C4-RA-1d", st in (201, 409), f"unknown field st={st}")
    applied = st == 201
    # RA-10: response shape
    ap = j(b) or {}
    if applied:
        expect("C4-RA-10", ap.get("plan_id") == pid
               and isinstance(ap.get("restaurant_revision"), int)
               and isinstance(ap.get("reservations"), list),
               f"apply shape {sorted(ap.keys())}")
        rs = ap.get("reservations") or []
        expect("C4-RA-10b", [r.get("reference") for r in rs] == [ref],
               f"reservations in ref order {[r.get('reference') for r in rs]}")
        expect("C4-RA-10c", rs and rs[0].get("table_ids") == ["t_b"],
               f"applied assignment {rs[0].get('table_ids') if rs else None}")
    # RA-2: unknown + foreign plan -> 404
    st, hd, b, _ = apply_plan(ada, "r_ops", "plan_nope")
    check_status("C4-RA-2a", st, 404, b)
    st, hd, b, _ = apply_plan(ada, "r_combo", pid)
    check_status("C4-RA-2b", st, 404, b)   # plan belongs to r_ops
    reset4()

def sec_ra_stale_replay():
    reset4()
    ada = mgr(); bob = nonmgr()
    base, ref, pl, st = _mk_plan(ada)
    pid = pl.get("plan_id")
    rev0 = pl.get("restaurant_revision")
    # RA-3: intervening revision-producing write stales the plan
    book(ada, "r_ops", local(base + timedelta(hours=5)), party=2,
         table="t_c")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    check_status("C4-RA-3", st, 409, b)
    expect("C4-RA-3b", err_code(b) == "stale_plan", f"code {err_code(b)}")
    st, hd, b, _ = call("GET", f"/reservations/{ref}", token=ada)
    rr = j(b) or {}
    expect("C4-RA-3c", rr.get("table_ids") == ["t_a"]
           and rr.get("revision") == 1,
           f"stale apply changed nothing {rr.get('table_ids')} rev={rr.get('revision')}")
    # non-revision writes do NOT stale: a fresh preview then a no-op PATCH
    reset4()
    ada = mgr()
    base, ref, pl, st = _mk_plan(ada)
    pid = pl.get("plan_id")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}",
                        body={"party_size": 2}, token=ada)  # no-op
    expect("C4-RA-3d", st == 200, f"noop patch st={st}")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    check_status("C4-RA-3e", st, 201, b)   # still applicable
    ap = j(b) or {}
    # RA-4: replay of apply key -> 200 original; different key -> 409
    st, hd, b2, _ = call("POST", f"/restaurants/r_ops/replans/{pid}/apply",
                         body={}, token=ada)  # no key reuse info; use same key
    # proper replay: use the ORIGINAL key — we did not keep it; do a fresh plan
    # RA-4 proper: new plan, apply with k, replay k, apply again with k2
    reset4()
    ada = mgr()
    base, ref, pl, st = _mk_plan(ada)
    pid = pl.get("plan_id")
    k = key()
    st, hd, b, _ = apply_plan(ada, "r_ops", pid, idem=k)
    check_status("C4-RA-4a", st, 201, b)
    orig = j(b)
    # later write to advance state
    book(ada, "r_ops", local(base + timedelta(hours=6)), party=1,
         table="t_c")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid, idem=k)
    expect("C4-RA-4b", st == 200 and j(b) == orig,
           f"apply replay returns original st={st}")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid, idem=key())
    check_status("C4-RA-4c", st, 409, b)
    expect("C4-RA-4d", err_code(b) == "plan_already_applied",
           f"code {err_code(b)}")
    reset4()

def sec_ra_revision_history():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(40 * 60)
    r1 = book(ada, "r_ops", local(base), party=2, table="t_a")
    r2 = book(ada, "r_ops", local(base), party=3, table="t_b")
    ref1 = ref_of(r1)
    ref2 = ref_of(r2)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": iso(base),
                           "to": iso(base + timedelta(hours=2))})
    pl = j(b) or {}
    rev_pre = pl.get("restaurant_revision")
    pid = pl.get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    check_status("C4-RA-6a", st, 201, b)
    ap = j(b) or {}
    # RA-9: exactly +1 for the whole apply
    expect("C4-RA-9", ap.get("restaurant_revision") == rev_pre + 1,
           f"restaurant rev {rev_pre} -> {ap.get('restaurant_revision')}")
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_c", "from": iso(base + timedelta(days=2)),
                           "to": iso(base + timedelta(days=2, hours=1))})
    expect("C4-RA-9b", (j(b) or {}).get("restaurant_revision") == rev_pre + 1,
           f"post-apply rev {((j(b) or {}).get('restaurant_revision'))}")
    # RA-7/8: moved booking got one reassigned entry, rev+1, terms intact
    st, hd, b, _ = hist(ref1, token=ada)
    ents = entries_of(b) or []
    reas = [e for e in ents if e.get("event") == "reassigned"]
    expect("C4-RA-7a", len(ents) == 2 and len(reas) == 1,
           f"history n={len(ents)} reassigned={len(reas)}")
    e = reas[0] if reas else {}
    ch = e.get("changes") or []
    expect("C4-RA-8", e.get("plan_id") == pid
           and ch == [{"field": "table_ids", "from": ["t_a"],
                       "to": ["t_c"]}],
           f"reassigned entry {e}")
    expect("C4-RA-8t", e.get("accepted_terms") is not None
           or (e.get("terms") is not None),
           f"reassigned entry carries accepted terms {sorted(e.keys())}")
    expect("C4-RA-8b", e.get("revision") == 2 and e.get("seq") == 2,
           f"entry rev/seq {e.get('revision')}/{e.get('seq')}")
    st, hd, b, _ = call("GET", f"/reservations/{ref1}", token=ada)
    rr = j(b) or {}
    expect("C4-RA-7b", rr.get("revision") == 2
           and rr.get("table_ids") == ["t_c"]
           and rr.get("accepted_terms", {}).get("policy_version") == 0
           and rr.get("starts_at_local") == local(base),
           f"moved booking rev2 t_c terms p0 {rr.get('table_ids')}")
    # unmoved booking untouched
    st, hd, b, _ = hist(ref2, token=ada)
    expect("C4-RA-8c", len(entries_of(b) or []) == 1,
           "unmoved booking gained no history")
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    expect("C4-RA-7c", (j(b) or {}).get("revision") == 1,
           "unmoved booking rev stays 1")
    reset4()

def sec_ra_closures():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(42 * 60)
    # close t_a over [base, base+2h) via applied plan
    r = book(bob, "r_ops", local(base), party=2, table="t_a")
    ref = ref_of(r)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": iso(base),
                           "to": iso(base + timedelta(hours=2))})
    pid = (j(b) or {}).get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    expect("C4-RA-11:setup", st == 201, f"apply st={st}")
    date = local(base)[:10]
    # RA-11: closed table excluded for EVERY overlapping slot; the slot at
    # the 'to' boundary (half-open) still offers it. Iterate all slots so
    # late-day fixtures can't flake on a missing grid point.
    st, hd, b, _ = avail("r_ops", date, 2)
    check_status("C4-RA-11z", st, 200, b)
    def _opts(sl):
        return [o["table_ids"] for o in
                (sl or {}).get("available_options", [])]
    win_lo, win_hi = local(base), local(base + timedelta(hours=2))
    inside = [s for s in (j(b) or {}).get("slots", [])
              if win_lo <= s.get("starts_at_local", "") < win_hi]
    at_hi = [s for s in (j(b) or {}).get("slots", [])
             if s.get("starts_at_local", "") == win_hi]
    ok_in = bool(inside) and all(
        ["t_a"] not in _opts(s) for s in inside)
    expect("C4-RA-11a", ok_in,
           f"{len(inside)} in-window slots exclude t_a")
    if at_hi:
        expect("C4-RA-11b", ["t_a"] in _opts(at_hi[0]),
               f"slot at 'to' boundary unaffected {_opts(at_hi[0])}")
    else:
        note("C4-RA-11b", "no slot exactly at 'to' boundary (late day)")
    # RA-12: conflicting create -> 409 table_unavailable
    st, hd, b, _ = book(bob, "r_ops", local(base + timedelta(minutes=30)),
                        party=2, table="t_a")
    check_status("C4-RA-12a", st, 409, b)
    expect("C4-RA-12b", err_code(b) == "table_unavailable",
           f"code {err_code(b)}")
    # create on other table ok
    st, hd, b, _ = book(bob, "r_ops", local(base + timedelta(minutes=30)),
                        party=2, table="t_c")
    expect("C4-RA-12c", st == 201, f"non-closed create st={st}")
    # move INTO closure conflicts
    r2 = book(bob, "r_ops", local(base + timedelta(hours=5)), party=2,
              table="t_c")
    ref2 = ref_of(r2)
    st, hd, b, _ = call("POST", "/reservation-moves", token=bob,
                        idem=key(),
                        body={"moves": [{"reference": ref2,
                                         "table_ids": ["t_a"],
                                         "starts_at_local":
                                         local(base + timedelta(minutes=30))}]})
    check_status("C4-RA-12d", st, 409, b)
    # amend into closure window on closed table — patch own booking
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}",
                        body={"table_id": "t_a",
                              "starts_at_local": local(base)},
                        token=bob)
    expect("C4-RA-12e", st == 409 and err_code(b) == "table_unavailable",
           f"amend into closure st={st} {err_code(b)}")
    # series adoption with a generated occurrence inside the closure fails
    wk = timedelta(days=7)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_c",
                           "from": iso(base + wk),
                           "to": iso(base + wk + timedelta(hours=2))})
    cpid = (j(b) or {}).get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_ops", cpid)
    expect("C4-RA-12s", st == 201, f"wk-out t_c closure applied st={st}")
    r3 = book(bob, "r_ops", local(base + timedelta(minutes=90)),
              party=2, table="t_c")
    ref3 = ref_of(r3)
    expect("C4-RA-12g", bool(ref3),
           f"anchor outside closure books st={r3[0]}")
    st, hd, b, _ = call("POST", "/series", token=bob, idem=key(),
                        body={"anchor_reference": ref3, "count": 2,
                              "interval_weeks": 1})
    expect("C4-RA-12h", st == 409 and err_code(b) == "table_unavailable",
           f"occurrence-in-closure adoption st={st} {err_code(b)}")
    st, hd, b, _ = call("GET", f"/reservations/{ref3}", token=bob)
    rr3 = j(b) or {}
    expect("C4-RA-12i", rr3.get("series_id") is None
           and rr3.get("revision") == 1,
           "failed adoption left anchor untouched")
    # RA-13: explain marks closure as no_overlap failure on t_a
    st, hd, b, _ = call(
        "GET", f"/availability?restaurant_id=r_ops&date={date}"
        f"&party_size=2&explain=true")
    sl = slot_at(b, local(base + timedelta(minutes=30)))
    if sl is None:
        # any in-window slot works; fall back to the first one inside
        wins13 = [s for s in (j(b) or {}).get("slots", [])
                  if local(base) <= s.get("starts_at_local", "")
                  < local(base + timedelta(hours=2))]
        sl = wins13[0] if wins13 else None
    ent = None
    for e in (sl or {}).get("explain", []):
        if e.get("table_id") == "t_a":
            ent = e
    rules = {r_["rule"]: r_["holds"] for r_ in (ent or {}).get("rules", [])}
    expect("C4-RA-13", ent is not None
           and rules.get("no_overlap") is False
           and ent.get("available") is False,
           f"closure reported no_overlap=false {ent}")
    # RA-15: a later preview must plan around an applied closure.
    # r_combo: p2 on t_a -> t_b/t_c tie on unused (2 each); rank prefers t_b.
    # Closing t_b first forces a correct plan onto t_c.
    reset4(); ada = mgr(); bob = nonmgr()
    base15 = dt_utc(45 * 60)
    st, hd, b, _ = replan(ada, "r_combo",
                          {"table_id": "t_b",
                           "from": iso(base15),
                           "to": iso(base15 + timedelta(hours=2))})
    c15 = (j(b) or {}).get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_combo", c15)
    expect("C4-RA-15a", st == 201, f"t_b closure applied st={st}")
    # R4-5: options CONTAINING t_b also blocked (pairs included)
    st, hd, b, _ = avail("r_combo", local(base15)[:10], 2)
    opts15 = [o["table_ids"] for s in (j(b) or {}).get("slots", [])
              if local(base15) <= s.get("starts_at_local", "")
              < local(base15 + timedelta(hours=2))
              for o in s.get("available_options", [])]
    expect("C4-RA-15x", opts15 and all("t_b" not in o for o in opts15),
           f"closed t_b purged incl. pairs {opts15[:6]}")
    st, hd, b, _ = book(bob, "r_combo", local(base15 + timedelta(minutes=30)),
                        party=2, table="t_a")
    r15 = (j(b) or {}).get("reference")
    expect("C4-RA-15b", bool(r15), f"p2 on t_a inside window st={st}")
    st, hd, b, _ = replan(ada, "r_combo",
                          {"table_id": "t_a",
                           "from": iso(base15),
                           "to": iso(base15 + timedelta(hours=2))})
    check_status("C4-RA-15c", st, 201, b)
    a15 = [a for a in (j(b) or {}).get("assignments", [])
           if a.get("reference") == r15]
    expect("C4-RA-15d", a15 and a15[0].get("table_ids") == ["t_c"],
           f"second plan respects applied t_b closure {a15}")
    # RA-14: closure at r_combo doesn't affect r_ops plan/availability
    reset4()
    ada = mgr()
    base = dt_utc(44 * 60)
    r = book(ada, "r_ops", local(base), party=2, table="t_a")
    ref = ref_of(r)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": iso(base),
                           "to": iso(base + timedelta(hours=2))})
    pid = (j(b) or {}).get("plan_id")
    # apply a closure at r_combo in between (its own revision channel)
    rb = book(ada, "r_combo", local(base), party=2, table="t_a")
    st, hd, b, _ = replan(ada, "r_combo",
                          {"table_id": "t_a", "from": iso(base),
                           "to": iso(base + timedelta(hours=2))})
    cpid = (j(b) or {}).get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_combo", cpid)
    expect("C4-RA-14a", st == 201, f"r_combo apply st={st}")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    expect("C4-RA-14b", st == 201,
           f"r_ops plan unaffected by foreign closure st={st} {err_code(b)}")
    # r_ops availability around the foreign closure window is intact:
    # every in-window slot still offers t_a (its own closure excepted  -- 
    # none applied on r_ops here)
    st, hd, b, _ = avail("r_ops", local(base)[:10], 2)
    wins = [s for s in (j(b) or {}).get("slots", [])
            if local(base) <= s.get("starts_at_local", "")
            < local(base + timedelta(hours=2))]
    def _o(sl):
        return [o["table_ids"] for o in
                (sl or {}).get("available_options", [])]
    ok = all(["t_a"] not in _o(s)
             and any(o != ["t_a"] for o in _o(s)) for s in wins)
    expect("C4-RA-14c", wins and ok,
           f"r_ops slots coherent across foreign closure {len(wins)} slots")
    reset4()

# ================= SA — series amendments =================

def _mk_series(tok, rid="r_ops", tbl="t_a", off=50 * 60, count=4,
               party=2, when=None):
    """Book + adopt weekly series; returns (base_dt, sid, refs, created_body)."""
    base = when or dt_utc(off)
    r = book(tok, rid, local(base), party=party, table=tbl)
    ref = ref_of(r)
    st, hd, b, _ = call("POST", "/series", token=tok, idem=key(),
                        body={"anchor_reference": ref, "count": count,
                              "interval_weeks": 1})
    sb = j(b) or {}
    refs = [o.get("reference") for o in sb.get("occurrences", [])]
    return base, sb.get("series_id"), refs, sb, st

def sec_sa_auth_validate():
    reset4()
    ada = mgr(); bob = nonmgr()
    base, sid, refs, sb, st = _mk_series(ada)
    expect("C4-SA-0", st == 201 and sid, f"series setup st={st} sid={sid}")
    body = {"expected_revision": 1, "from_index": 1, "local_time": "20:00"}
    # SA-1: auth + ownership
    st, hd, b, _ = call("POST", f"/series/{sid}/amend", body=body)
    check_status("C4-SA-1a", st, 401, b)
    st, hd, b, _ = amend_series("bogus-token", sid, body)
    check_status("C4-SA-1b", st, 401, b)
    st, hd, b, _ = amend_series(ada, "ser_nope", body)
    check_status("C4-SA-1c", st, 404, b)
    st, hd, b, _ = amend_series(bob, sid, body)   # foreign owner
    check_status("C4-SA-1d", st, 404, b)
    st, hd, b, _ = call("POST", f"/series/{sid}/amend",
                        body=body, token=ada)   # missing key
    check_status("C4-SA-1e", st, 400, b)
    # SA-2: missing fields -> 422; unknown field ignored
    for f in ("expected_revision", "from_index", "local_time"):
        req = dict(body); req.pop(f)
        st, hd, b, _ = amend_series(ada, sid, req)
        check_status(f"C4-SA-2:{f}", st, 422, b)
    req = dict(body); req["junk"] = "x"
    st, hd, b, _ = amend_series(ada, sid, req)
    expect("C4-SA-2b", st in (201, 409), f"unknown field st={st}")
    # SA-3: expected_revision / from_index sweeps
    for v in (0, -1, 1.5, "1", True, None, [1]):
        req = dict(body); req["expected_revision"] = v
        st, hd, b, _ = amend_series(ada, sid, req)
        check_status(f"C4-SA-3:rev={v!r}", st, 422, b)
    for v in (-1, 4, 99, 1.5, "1", True, None):
        req = dict(body); req["from_index"] = v
        st, hd, b, _ = amend_series(ada, sid, req)
        check_status(f"C4-SA-3:idx={v!r}", st, 422, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    cur_rev = (j(b) or {}).get("revision")
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": cur_rev,
                                 "from_index": 3, "local_time": "21:00"})
    expect("C4-SA-3b", st == 201,
           f"from_index=count-1 boundary st={st} (rev {cur_rev})")
    # SA-4: local_time sweep (use current series rev so a malformed
    # body must 422 rather than trip a stale_revision short-circuit)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    cur_rev = (j(b) or {}).get("revision")
    for v in ("9:00", "24:00", "23:60", "2000", "20:0", "ab:cd", 2000,
              None, True, "20:00:00", " 20:00"):
        req = {"expected_revision": cur_rev, "from_index": 0,
               "local_time": v}
        st, hd, b, _ = amend_series(ada, sid, req)
        check_status(f"C4-SA-4:{v!r}", st, 422, b)
    reset4()

def sec_sa_behavior():
    reset4()
    ada = mgr(); bob = nonmgr()
    base, sid, refs, sb, st = _mk_series(ada)
    # SA-5: stale revision before occurrence validation (R4-19)
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 99, "from_index": 0,
                                 "local_time": "21:00"})
    check_status("C4-SA-5", st, 409, b)
    expect("C4-SA-5b", err_code(b) == "stale_revision", f"code {err_code(b)}")
    # SA-6/7: cancel idx3, mark idx2 exception (PATCH), amend from_index=1
    call("POST", f"/reservations/{refs[3]}/cancel", body={}, token=ada)
    call("PATCH", f"/reservations/{refs[2]}", body={"party_size": 3},
         token=ada)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    srev = (j(b) or {}).get("revision")
    # pick a target clock != the anchor's own, so the amend is a real change
    orig_hm0 = local(base)[-5:]
    tgt_hm = "21:00" if orig_hm0 != "21:00" else "22:15"
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": srev,
                                 "from_index": 1, "local_time": tgt_hm})
    check_status("C4-SA-6a", st, 201, b)
    am = j(b) or {}
    occ = {o["index"]: o for o in am.get("occurrences", [])}
    # idx0 anchor untouched (before from_index); idx1 moved to 21:00;
    # idx2 exception kept own time; idx3 cancelled unchanged
    def occ_time(i):
        o = occ.get(i) or {}
        r = o.get("reservation") or {}
        return r.get("starts_at_local", "")
    orig_hm = local(base)[-5:]
    expect("C4-SA-7a", occ_time(0).endswith(orig_hm)
           and occ_time(1).endswith(tgt_hm),
           f"idx0 {occ_time(0)} idx1 {occ_time(1)} (orig {orig_hm})")
    expect("C4-SA-6b", occ_time(2).endswith(orig_hm)
           and occ.get(2, {}).get("exception") is True,
           f"exception idx2 untouched {occ_time(2)}")
    expect("C4-SA-6c", (occ.get(3, {}).get("reservation") or {})
           .get("status") == "cancelled",
           "cancelled idx3 untouched")
    # identity preserved: same refs, date part unchanged
    d1 = local(base + timedelta(days=7))[:10]
    expect("C4-SA-7b", occ_time(1).startswith(d1),
           f"clock-time only, date kept {occ_time(1)} want {d1}")
    expect("C4-SA-7c", [o.get("reference") for o in am.get("occurrences", [])]
           == refs, "references preserved in order")
    # SA-13: full series response in index order
    expect("C4-SA-13", [o.get("index") for o in am.get("occurrences", [])]
           == sorted(o.get("index") for o in am.get("occurrences", []))
           and am.get("series_id") == sid,
           f"response in index order")
    # SA-14/15: changed occurrence history + revisions; series rev +1 once
    st, hd, b, _ = hist(refs[1], token=ada)
    ents = entries_of(b) or []
    expect("C4-SA-14", ents and ents[-1].get("event") == "changed"
           and any(c.get("field") == "starts_at_local" for c in
                   ents[-1].get("changes", [])),
           f"occurrence history {ents[-1] if ents else None}")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C4-SA-15", (j(b) or {}).get("revision") == srev + 1,
           f"series rev {srev} -> {(j(b) or {}).get('revision')}")
    # SA-16: amend did not mark exceptions
    expect("C4-SA-16", all(o.get("exception") is False
           for i, o in occ.items() if i != 2),
           f"exception flags {[o.get('exception') for o in am['occurrences']]}")
    # SA-8/17: amend to same clock time -> all no-op, rev unchanged
    srev2 = (j(b) or {}).get("revision")
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": srev2,
                                 "from_index": 1, "local_time": tgt_hm})
    expect("C4-SA-8", st == 201, f"no-op amend st={st}")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C4-SA-8b", (j(b) or {}).get("revision") == srev2,
           "no-op amend kept series revision")
    # SA-17: empty eligible set (from_index past all eligible) -> success
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": srev2,
                                 "from_index": 3, "local_time": "22:00"})
    expect("C4-SA-17", st == 201, f"empty-eligible set st={st}")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C4-SA-17b", (j(b) or {}).get("revision") == srev2,
           "empty-eligible amend kept revision")
    reset4()

def sec_sa_conflicts_atomicity():
    reset4()
    ada = mgr(); bob = nonmgr()
    # SA-9: each occurrence checks its OLD accepted cutoff first.
    # Organic occurrence-inside-cutoff is unreachable: adoption itself
    # refuses anchors inside their cutoff, and every later occurrence is
    # further out than the anchor. So SEED the state via export/import:
    # pull occurrence idx0 to ~45min out (inside its 120min accepted
    # cutoff), then amend.
    base, sid, refs, sb, st = _mk_series(ada)
    expect("C4-SA-9a", st == 201 and sid, f"series st={st} sid={sid}")
    st, exp = export_state()
    res = (exp or {}).get("state", {}).get("reservations", {})
    r0 = next((r for r in res.values()
               if r.get("reference") == refs[0]), None)
    expect("C4-SA-9a2", r0 is not None, "idx0 reservation in export")
    soon = datetime.now(timezone.utc) + timedelta(minutes=45)
    soon = soon.replace(second=0, microsecond=0)
    dur = int((r0.get("accepted_terms") or {})
              .get("reservation_duration_minutes", 60))
    end = soon + timedelta(minutes=dur)
    r0["starts_at_local"] = soon.strftime("%Y-%m-%dT%H:%M")
    r0["starts_at"] = soon.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r0["ends_at"] = end.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r0["start_epoch"] = soon.timestamp()
    r0["end_epoch"] = end.timestamp()
    st, hd, b, _ = call("POST", "/_test/import", raw=json.dumps(exp))
    expect("C4-SA-9a3", st == 204, f"seed import st={st}")
    # idx0 now inside its 120min accepted cutoff -> amending it must fail
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 1, "from_index": 0,
                                 "local_time": "21:15"})
    check_status("C4-SA-9b", st, 409, b)
    expect("C4-SA-9c", err_code(b) == "cutoff_passed",
           f"idx0 inside cutoff -> cutoff_passed, got {err_code(b)}")
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 1, "from_index": 1,
                                 "local_time": "21:15"})
    expect("C4-SA-9d", st == 201,
           f"skipping the inside-cutoff occurrence succeeds st={st}")
    # SA-5 precedence: stale rev beats cutoff even when idx0 would fail
    reset4(); ada = mgr()
    base, sid, refs, sb, st = _mk_series(ada)
    st, exp = export_state()
    res = (exp or {}).get("state", {}).get("reservations", {})
    r0 = next((r for r in res.values()
               if r.get("reference") == refs[0]), None)
    soon = datetime.now(timezone.utc) + timedelta(minutes=45)
    soon = soon.replace(second=0, microsecond=0)
    end = soon + timedelta(minutes=60)
    r0["starts_at_local"] = soon.strftime("%Y-%m-%dT%H:%M")
    r0["starts_at"] = soon.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r0["ends_at"] = end.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r0["start_epoch"] = soon.timestamp()
    r0["end_epoch"] = end.timestamp()
    call("POST", "/_test/import", raw=json.dumps(exp))
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 7, "from_index": 0,
                                 "local_time": "21:15"})
    expect("C4-SA-5c", st == 409 and err_code(b) == "stale_revision",
           f"stale beats cutoff st={st} {err_code(b)}")
    # SA-10/12: occupancy conflict after all non-occupancy checks
    reset4(); ada = mgr(); bob = nonmgr()
    base, sid, refs, sb, st = _mk_series(ada)          # weekly x4 on t_a
    wk = timedelta(days=7)
    # block the amend target: book t_a at idx1's resulting time using the
    # occurrence's OWN stored utc offset so the instants truly overlap
    st, hd, b, _ = call("GET", f"/reservations/{refs[1]}", token=ada)
    sl1 = (j(b) or {}).get("starts_at_local", "")
    # stored starts_at_local echoes the naive local format  --  reuse its date
    tgt = sl1[:10] + "T22:15"
    st, hd, b, _ = book(bob, "r_ops", tgt, party=2, table="t_a")
    expect("C4-SA-10a", st == 201, f"blocker booking st={st}")
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 1, "from_index": 1,
                                 "local_time": "22:15"})
    check_status("C4-SA-10b", st, 409, b)
    expect("C4-SA-10c", err_code(b) == "table_unavailable",
           f"occupancy conflict st={st} {err_code(b)}")
    # SA-11: atomic — idx1 unchanged, series rev unchanged, key reusable
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    sb2 = j(b) or {}
    occ1 = [o for o in sb2.get("occurrences", []) if o.get("index") == 1]
    rtime = (occ1[0].get("reservation") or {}).get("starts_at_local", "")
    expect("C4-SA-11a", sb2.get("revision") == 1
           and rtime.endswith(local(base)[-5:]),
           f"failed amend changed nothing rev={sb2.get('revision')} t={rtime}")
    st, hd, b, _ = hist(refs[1], token=ada)
    expect("C4-SA-11b", len(entries_of(b) or []) == 1,
           "no history entries written by failed amend")
    # SA-12: non-occupancy error at earlier index wins over occupancy.
    # Make idx1 invalid (on t_a, conflict above) and idx2 also blocked;
    # also craft idx1's clock to be off-grid after a policy publish? Simpler:
    # idx1 cutoff cannot be arranged; use index order among two conflicts
    # is unknowable -> instead check invalid-vs-occupancy precedence with a
    # policy that makes idx1's resulting time off-grid.
    publish(ada, "r_ops", pol(eff=sl1[:10], slot=30))
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": 1, "from_index": 1,
                                 "local_time": "22:15"})
    # idx1 falls under new 30-min policy -> 22:15 off grid -> 422 before
    # any occupancy decision
    expect("C4-SA-12", st == 422 and err_code(b) in ("not_on_slot_grid",
                                                     "validation_failed"),
           f"policy-grid error precedes occupancy st={st} {err_code(b)}")
    reset4()

def sec_sa_replay_race():
    reset4()
    ada = mgr(); bob = nonmgr()
    base, sid, refs, sb, st = _mk_series(ada)
    body = {"expected_revision": 1, "from_index": 2, "local_time": "21:45"}
    st, hd, b1, _ = amend_series(ada, sid, body, idem="SA-R1")
    check_status("C4-SA-18a", st, 201, b1)
    # later edit + cancel, then replay the ORIGINAL key
    call("PATCH", f"/reservations/{refs[0]}", body={"party_size": 4},
         token=ada)
    call("POST", f"/reservations/{refs[3]}/cancel", body={}, token=ada)
    st, hd, b2, _ = amend_series(ada, sid, body, idem="SA-R1")
    expect("C4-SA-18b", st == 200 and j(b2) == j(b1),
           f"replay after later edits returns original st={st}")
    # different key with now-stale revision -> stale
    st, hd, b, _ = amend_series(ada, sid, body)
    expect("C4-SA-18c", st == 409 and err_code(b) == "stale_revision",
           f"fresh key stale st={st}")
    # SA-19: same-expected-revision race — at most one may make real change
    reset4(); ada = mgr()
    base, sid, refs, sb, st = _mk_series(ada)
    res = []
    def _go(t):
        st, hd, b, _ = amend_series(
            ada, sid, {"expected_revision": 1, "from_index": 1,
                       "local_time": t})
        res.append((st, j(b) or {}))
    ths = [threading.Thread(target=_go, args=(t,))
           for t in ("22:00", "22:30")]
    for t in ths: t.start()
    for t in ths: t.join(15)
    codes = sorted(s for s, _ in res)
    real = sum(1 for s, _ in res if s == 201)
    expect("C4-SA-19", real <= 1
           and all(s in (201, 409) for s, _ in res),
           f"amend race results {codes}")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C4-SA-19b", (j(b) or {}).get("revision") == 1 + real,
           f"series rev consistent rev={(j(b) or {}).get('revision')}")
    reset4()

def sec_sa_repair():
    """SA-20/R4-22: replan moving a series occurrence keeps its series
    membership, flags and terms; series revision +1 once per application."""
    reset4()
    ada = mgr(); bob = nonmgr()
    base, sid, refs, sb, st = _mk_series(ada)
    # exception-flag idx1
    call("PATCH", f"/reservations/{refs[1]}", body={"party_size": 3},
         token=ada)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    srev = (j(b) or {}).get("revision")
    win0 = base + timedelta(days=7); win1 = win0 + timedelta(hours=2)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a",
                           "from": iso(win0), "to": iso(win1)})
    check_status("C4-SA-20a", st, 201, b)
    pid = (j(b) or {}).get("plan_id")
    moved = [a["reference"] for a in (j(b) or {}).get("assignments", [])
             if a.get("changed")]
    expect("C4-SA-20b", refs[1] in moved,
           f"occurrence idx1 in plan moved={moved}")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    check_status("C4-SA-20c", st, 201, b)
    # occurrence kept ref, exception flag, series membership
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    sb2 = j(b) or {}
    o1 = [o for o in sb2.get("occurrences", []) if o.get("index") == 1]
    expect("C4-SA-20d", o1 and o1[0].get("exception") is True
           and o1[0].get("reference") == refs[1],
           f"flags+ref preserved {o1}")
    expect("C4-SA-20e", sb2.get("revision") == srev + 1,
           f"series rev +1: {srev} -> {sb2.get('revision')}")
    # reservation revision bumped exactly once, accepted terms kept
    st, hd, b, _ = call("GET", f"/reservations/{refs[1]}", token=ada)
    rr = j(b) or {}
    expect("C4-SA-20f", rr.get("revision") == 3,    # patch=2, apply=3
           f"occurrence revision {rr.get('revision')}")
    expect("C4-SA-20g", (rr.get("accepted_terms") or {}).get(
           "cancellation_cutoff_minutes") is not None,
           "accepted terms retained on moved occurrence")
    reset4()

def sec_rp_pairs_unused():
    """R4-8 declared-pair candidates after singletons; R4-9 unused_seats
    counts every considered booking, moved or not."""
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(46 * 60)
    # p5 at r_combo can't fit any singleton -> only pair [t_b,t_c] can host
    # once t_a closes (pair [t_a,t_b] contains the closing table).
    st, hd, b, _ = book(bob, "r_combo", local(base), party=5,
                        ids=["t_a", "t_b"])
    ref5 = (j(b) or {}).get("reference")
    expect("C4-RP-20a", st == 201, f"pair booking setup st={st}")
    st, hd, b, _ = replan(ada, "r_combo",
                          {"table_id": "t_a",
                           "from": iso(base), "to": iso(base
                                                    + timedelta(hours=2))})
    check_status("C4-RP-20b", st, 201, b)
    asg = {a["reference"]: a["table_ids"]
           for a in (j(b) or {}).get("assignments", [])}
    expect("C4-RP-20c", asg.get(ref5) == ["t_b", "t_c"],
           f"pair candidate chosen, t_b,t_c free of closures {asg}")
    # R4-9: considered-but-unmoved bookings still count toward unused_seats
    reset4(); ada = mgr(); bob = nonmgr()
    base = dt_utc(44 * 60)
    r1 = book(bob, "r_ops", local(base), party=2, table="t_a")
    r2 = book(bob, "r_ops", local(base + timedelta(minutes=30)),
              party=2, table="t_b")
    ref1 = ref_of(r1)
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a",
                           "from": iso(base), "to": iso(base
                                                    + timedelta(hours=2))})
    check_status("C4-RP-21a", st, 201, b)
    pb = j(b) or {}
    # t_a closes -> r1 must move; t_b is held by r2 at the same instant,
    # so r1 lands on t_c(8): unused 6; r2 stays t_b(4): unused 2 -> 8.
    caps = {"t_a": 4, "t_b": 4, "t_c": 8}
    parties = {ref1: 2, ref_of(r2): 2}
    expect("C4-RP-21b", pb.get("moved_count") == 1,
           f"moved_count {pb.get('moved_count')} assignments="
           f"{pb.get('assignments')}")
    # unused_seats sums (candidate capacity - party) over EVERY considered
    # booking, moved or not
    exp = 0
    for a in pb.get("assignments", []):
        cap = sum(caps.get(t, 0) for t in a.get("table_ids", []))
        exp += cap - parties.get(a["reference"], 0)
    expect("C4-RP-21c", pb.get("unused_seats") == exp,
           f"unused_seats {pb.get('unused_seats')} want {exp}")
    reset4()

def sec_sa_vs_closure():
    """SA-10b: series amend resulting occurrence onto an applied closure
    must fail 409 table_unavailable (closures are occupancy, R4-15).

    Deterministic layout: anchor at a fixed morning instant so a closure
    can cover a LATER clock window on an occurrence's own date without
    overlapping the occurrence itself (so the plan leaves it on t_a)."""
    reset4()
    ada = mgr(); bob = nonmgr()
    base = (datetime.now(timezone.utc) + timedelta(days=9)).replace(
        hour=10, minute=0, second=0, microsecond=0)
    base0, sid, refs, sb, st = _mk_series(ada, when=base)
    expect("C4-SA-21a", st == 201, f"morning series st={st}")
    # closure on t_a covering idx1's DATE at 14:00-16:00  --  the occurrence
    # sits at 10:00-11:00 that day, so the plan does NOT move it.
    win0 = base + timedelta(days=7, hours=4)   # same date as idx1, 14:00
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": iso(win0),
                           "to": iso(win0 + timedelta(hours=2))})
    check_status("C4-SA-21b", st, 201, b)
    pid = (j(b) or {}).get("plan_id")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    expect("C4-SA-21c", st == 201, f"closure apply st={st}")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    srev = (j(b) or {}).get("revision")
    # amend clock to 14:30 for idx>=1 -> idx1 lands inside the closure
    st, hd, b, _ = amend_series(ada, sid,
                                {"expected_revision": srev,
                                 "from_index": 1, "local_time": "14:30"})
    expect("C4-SA-21d", st == 409 and err_code(b) == "table_unavailable",
           f"amend into closure st={st} {err_code(b)}")
    # atomicity: series revision and occurrence times unchanged
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    sb2 = j(b) or {}
    o1 = [o for o in sb2.get("occurrences", []) if o.get("index") == 1]
    rt = (o1[0].get("reservation") or {}).get("starts_at_local", "")
    expect("C4-SA-21e", sb2.get("revision") == srev
           and rt.endswith("10:00"),
           f"failed amend left series intact rev={sb2.get('revision')} "
           f"idx1={rt}")
    reset4()


# ================= CON — stage-4 concurrency / atomicity =================

def sec_concurrency4():
    reset4()
    ada = mgr(); bob = nonmgr()
    base = dt_utc(40 * 60)
    frm, to = iso(base), iso(base + timedelta(hours=2))
    # CON-1: two PENDING previews coexist (preview does not bump revision)
    st1, hd, b1, _ = replan(ada, "r_ops",
                            {"table_id": "t_a", "from": frm, "to": to})
    st2, hd, b2, _ = replan(ada, "r_ops",
                            {"table_id": "t_b", "from": frm, "to": to})
    p1, p2 = (j(b1) or {}).get("plan_id"), (j(b2) or {}).get("plan_id")
    expect("C4-CON-1a", st1 == 201 and st2 == 201 and p1 and p2 and p1 != p2,
           f"two pending plans st={st1},{st2} ids={p1},{p2}")
    # CON-1b: racing applies of the SAME plan under different keys —
    # exactly one 201; the loser sees plan_already_applied
    res = []
    def _ap(k):
        st, hd, b, _ = apply_plan(ada, "r_ops", p1, idem=k)
        res.append((st, err_code(b)))
    ths = [threading.Thread(target=_ap, args=(f"ap{i}",))
           for i in range(2)]
    for t in ths: t.start()
    for t in ths: t.join(15)
    got201 = sum(1 for s, c in res if s == 201)
    expect("C4-CON-1b", got201 == 1
           and all(c in (None, "plan_already_applied", "stale_plan")
                   for s, c in res),
           f"double-apply race {res}")
    # CON-1c: applying the other plan now -> stale (revision moved by apply)
    st, hd, b, _ = apply_plan(ada, "r_ops", p2)
    expect("C4-CON-1c", st == 409 and err_code(b) == "stale_plan",
           f"second plan stale after first apply st={st} {err_code(b)}")
    # CON-2: apply vs concurrent booking create on the closing table —
    # whichever lands first is internally consistent afterwards
    reset4(); ada = mgr(); bob = nonmgr()
    r = book(bob, "r_ops", local(base), party=2, table="t_a")
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to})
    pid = (j(b) or {}).get("plan_id")
    out = {}
    def _apply():
        out["ap"] = apply_plan(ada, "r_ops", pid)[0]
    def _create():
        out["cr"] = book(bob, "r_ops",
                         local(base + timedelta(minutes=30)),
                         party=2, table="t_a")[0]
    ths = [threading.Thread(target=_apply),
           threading.Thread(target=_create)]
    for t in ths: t.start()
    for t in ths: t.join(15)
    # A create bumps restaurant revision -> if it landed before apply, the
    # plan is stale; if after, the closure blocks it. Both can never win.
    ok_race = ((out.get("ap") == 201 and out.get("cr") == 409)
               or (out.get("cr") == 201
                   and out.get("ap") == 409))
    expect("C4-CON-2a", ok_race,
           f"apply/create race outcome legal {out}")
    if out.get("cr") == 201:
        # verify the stale code was the plan's, not a generic conflict
        st, hd, b, _ = apply_plan(ada, "r_ops", pid, idem="con2retry")
        expect("C4-CON-2b", err_code(b) == "stale_plan",
               f"lost plan reports stale_plan {err_code(b)}")
    # CON-3: booking write that lands before apply must invalidate the plan
    reset4(); ada = mgr(); bob = nonmgr()
    r = book(bob, "r_ops", local(base), party=2, table="t_a")
    st, hd, b, _ = replan(ada, "r_ops",
                          {"table_id": "t_a", "from": frm, "to": to})
    pid = (j(b) or {}).get("plan_id")
    st, hd, b, _ = book(bob, "r_ops",
                        local(base + timedelta(hours=4)),  # outside window
                        party=2, table="t_b")
    expect("C4-CON-3a", st == 201, f"intervening create st={st}")
    st, hd, b, _ = apply_plan(ada, "r_ops", pid)
    expect("C4-CON-3b", st == 409 and err_code(b) == "stale_plan",
           f"plan stale after ANY revision write st={st} {err_code(b)}")
    reset4()

# ================= D-3 — hardened mode (separate instance) =================

def sec_hardened4():
    for m, p in (("POST", "/_test/reset"), ("GET", "/_test/export"),
                 ("POST", "/_test/import")):
        st, hd, b, _ = call(m, p, body={} if m == "POST" else None)
        check_status(f"C4-HRD:{p}", st, 404, b)
    st, hd, b, _ = call("GET", "/health")
    check_status("C4-HRD-health", st, 200, b)
    st, hd, b, _ = call("GET", "/")
    ct = hd.get("Content-Type") or hd.get("content-type") or ""
    expect("C4-HRD-ui", st == 200 and "text/html" in ct.lower(),
           f"UI still served st={st} ct={ct!r}")

def sec_ra_stale_matrix():
    """R4-12 coherence: each write type either bumps restaurant_revision
    (then apply must fail stale_plan) or doesn't (apply must proceed).
    Spec: revision bumps on new booking, real amendment, cancellation,
    policy publication, plan application; not on no-ops/failures."""
    def _rev_probe(ada):
        far = dt_utc(60 * 24 * 30)          # ~30d out, empty window
        st, hd, b, _ = replan(ada, "r_ops",
                              {"table_id": "t_b", "from": iso(far),
                               "to": iso(far + timedelta(hours=1))})
        return (j(b) or {}).get("restaurant_revision")
    def w_create(ada, base, ref):
        return book(ada, "r_ops", local(base + timedelta(hours=6)),
                    party=1, table="t_c")
    def w_patch(ada, base, ref):
        return call("PATCH", f"/reservations/{ref}",
                    body={"party_size": 3}, token=ada)
    def w_cancel(ada, base, ref):
        return call("POST", f"/reservations/{ref}/cancel",
                    body={}, token=ada)
    def w_move(ada, base, ref):
        return call("POST", "/reservation-moves", token=ada, idem=key(),
                    body={"moves": [{"reference": ref,
                                     "table_ids": ["t_b"],
                                     "expected_revision": 1}]})
    def w_policy(ada, base, ref):
        return publish(ada, "r_ops",
                       pol(eff=local(base + timedelta(days=2))[:10],
                           cut=90))
    def w_series(ada, base, ref):
        return call("POST", "/series", token=ada, idem=key(),
                    body={"anchor_reference": ref, "count": 2,
                          "interval_weeks": 1})
    for name, fn in (("create", w_create), ("patch", w_patch),
                     ("cancel", w_cancel), ("move", w_move),
                     ("policy", w_policy), ("series_create", w_series)):
        reset4()
        ada = mgr()
        base, ref, pl, st = _mk_plan(ada)
        pid = pl.get("plan_id")
        rev_pre = pl.get("restaurant_revision")
        wst, hd, b, _ = fn(ada, base, ref)
        expect(f"C4-RA-SM:{name}:write", wst in (200, 201),
               f"write '{name}' itself st={wst} {err_code(b)}")
        rev_now = _rev_probe(ada)
        bumped = isinstance(rev_now, int) and isinstance(rev_pre, int)             and rev_now > rev_pre
        st, hd, b, _ = apply_plan(ada, "r_ops", pid)
        if bumped:
            expect(f"C4-RA-SM:{name}",
                   st == 409 and err_code(b) == "stale_plan",
                   f"rev {rev_pre}->{rev_now} but apply st={st} "
                   f"{err_code(b)}")
            # the plan itself did not apply: no `reassigned` history entry
            # (a write like 'move' may itself have relocated the booking)
            st, hd, b, _ = hist(ref, token=ada)
            reas = [e for e in (entries_of(b) or [])
                    if e.get("event") == "reassigned"]
            expect(f"C4-RA-SM:{name}:atomic", len(reas) == 0,
                   f"stale apply left reassigned entries {reas}")
        else:
            expect(f"C4-RA-SM:{name}",
                   err_code(b) != "stale_plan",
                   f"non-bumping write (rev {rev_pre}->{rev_now}) "
                   f"staled plan anyway st={st}")
    reset4()

SECTIONS4 = [sec_rp_auth, sec_rp_considered, sec_rp_plan,
             sec_rp_limits_effects, sec_rp_pairs_unused,
             sec_ra_apply, sec_ra_stale_replay, sec_ra_revision_history,
             sec_ra_stale_matrix,
             sec_ra_closures,
             sec_sa_auth_validate, sec_sa_behavior,
             sec_sa_conflicts_atomicity, sec_sa_replay_race, sec_sa_repair,
             sec_sa_vs_closure,
             sec_concurrency4]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=s1.BASE)
    ap.add_argument("--only", default=None, help="substring filter on section name")
    ap.add_argument("--inherited-only", action="store_true")
    ap.add_argument("--s4-only", action="store_true")
    ap.add_argument("--hardened", action="store_true",
                    help="target is a hardened instance: run only hardening probes")
    args = ap.parse_args()
    s1.BASE = args.base_url.rstrip("/")
    t0 = time.monotonic()
    if args.hardened:
        sections = [sec_hardened4]
    elif args.inherited_only:
        sections = list(s1.SECTIONS) + s2.SECTIONS2 + s3.SECTIONS3
    elif args.s4_only:
        sections = SECTIONS4
    else:
        sections = (list(s1.SECTIONS) + s2.SECTIONS2 +
                    list(s3.SECTIONS3) + SECTIONS4)
    for s in sections:
        if args.only and args.only not in s.__name__:
            continue
        try:
            s()
        except Exception as e:
            expect(s.__name__, False, f"check raised {e!r}")
    fails = [r for r in s1.RESULTS if not r[1]]
    print(f"\n== {len(s1.RESULTS)} checks, {len(fails)} FAIL, "
          f"{len(s1.FIVE_XX)} 5xx/conn-errors, {time.monotonic()-t0:.1f}s ==")
    for cid, ok, d in fails:
        print("FAIL", cid, "-", d)
    for cid, st in s1.FIVE_XX:
        print("5XX", cid, "-", st)
    sys.exit(1 if fails or s1.FIVE_XX else 0)

if __name__ == "__main__":
    main()

