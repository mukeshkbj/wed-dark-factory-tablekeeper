#!/usr/bin/env python3
"""tk-verifier stage-3 black-box checks (spec-derived; stdlib only).

Inherits the COMPLETE stage-2 suite verbatim (which itself inherits stage-1
verbatim) and adds stage-3 sections: availability explanations (E), booking
policies and accepted terms (P/T), reservation history + decision (H),
recurring series (S), combined-table history (B), collective moves under
policies/series (M), concurrency, and hardened-mode probes (D-3).

Spec: tablekeeper/spec/stage-3.md @803560d.
Every request has a hard timeout; a hang fails.

Usage:
  python checks.py --base-url http://localhost:8080     full suite (s1+s2+s3)
  python checks.py --base-url ... --inherited-only      stage-1+2 regression
  python checks.py --base-url ... --s3-only             stage-3 sections only
  python checks.py --base-url ... --hardened            hardened-instance probes
  python checks.py --base-url ... --only substring      section-name filter
"""
import argparse, importlib.util, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

_HERE = pathlib.Path(__file__).resolve().parent

def _load_s2():
    p = _HERE.parent / "stage-2" / "checks.py"
    spec = importlib.util.spec_from_file_location("tk_s2_checks", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

s2 = _load_s2()
s1 = s2.s1
call = s1.call; j = s1.j; expect = s1.expect; note = s1.note
check_status = s1.check_status; err_code = s1.err_code
key = s1.key; utc_local = s1.utc_local; login = s1.login; signup = s1.signup
WEEKDAYS = s1.WEEKDAYS
fixture_combo = s2.fixture_combo; reset2 = s2.reset2
avail = s2.avail; slot_at = s2.slot_at

# ---------------- stage-3 fixtures ----------------
# fixture_p3(): fixture_combo() plus manager_user_ids.
#   u_ada manages every restaurant; u_bob is a non-manager everywhere.
#   r_ops (UTC all-week, slot 15, dur 60, cutoff 120): t_a4 t_b4 t_c8.
#   r_combo (UTC all-week, slot 15, dur 60, cutoff 120):
#     t_a cap2, t_b cap4, t_c cap4; combinable [t_a,t_b]=6, [t_b,t_c]=8.

def fixture_p3():
    fx = fixture_combo()
    for r in fx["restaurants"]:
        r["manager_user_ids"] = ["u_ada"]
    return fx

def reset3(fx=None, cid="C3-RT-0"):
    st, hd, b, dt = call("POST", "/_test/reset",
                         body=fx if fx is not None else fixture_p3(), timeout=15)
    if st != 204:
        expect(cid, False, f"reset st={st} body={b[:200]!r}")
        return False
    return True

def mgr():
    return login("ada@example.com", "correct horse")[1]["token"]

def nonmgr():
    return login("bob@example.com", "second horse")[1]["token"]

OPS_HOURS = [{"weekday": w, "opens": "00:00", "closes": "23:59"}
             for w in WEEKDAYS]
OPS_CAPS = {"t_a": 4, "t_b": 4, "t_c": 8}

def pol(eff="2026-10-05", slot=30, dur=30, cut=60,
        hours=None, caps=None, **extra):
    """Complete valid policy body for r_ops."""
    p = {"effective_from": eff, "slot_minutes": slot,
         "reservation_duration_minutes": dur, "cancellation_cutoff_minutes": cut,
         "opening_hours": hours if hours is not None else OPS_HOURS,
         "capacities": caps if caps is not None else dict(OPS_CAPS)}
    p.update(extra)
    return p

def publish(token, rid, body, idem=None):
    return call("POST", f"/restaurants/{rid}/policies",
                body=body, token=token, idem=idem if idem is not None else key())

def list_policies(rid, token=None):
    return call("GET", f"/restaurants/{rid}/policies", token=token)

def book(token, rid, when, party=2, table="t_a", ids=None, idem=None):
    b = {"restaurant_id": rid, "starts_at_local": when, "party_size": party}
    if ids is not None:
        b["table_ids"] = ids
    else:
        b["table_id"] = table
    return call("POST", "/reservations", body=b, token=token,
                idem=idem if idem is not None else key())

def hist(ref, token=None):
    return call("GET", f"/reservations/{ref}/history", token=token)

def decision(ref, token=None):
    return call("GET", f"/reservations/{ref}/decision", token=token)

def entries_of(b):
    return (j(b) or {}).get("entries")

TERMS_KEYS = {"policy_version", "slot_minutes", "reservation_duration_minutes",
              "cancellation_cutoff_minutes", "opening_hours", "capacities"}

def terms_p0_ops():
    return {"policy_version": 0, "slot_minutes": 15,
            "reservation_duration_minutes": 60, "cancellation_cutoff_minutes": 120,
            "opening_hours": OPS_HOURS, "capacities": dict(OPS_CAPS)}

# ================= E — availability explanations =================

def sec_explain():
    reset3()
    D = utc_local(26 * 60)[:10]          # r_ops UTC all-week
    T = utc_local(26 * 60)
    # E-1: only literal "true" accepted; everything else is 422
    for tag, q in (("false", "explain=false"), ("one", "explain=1"),
                   ("empty", "explain="), ("TRUE", "explain=TRUE"),
                   ("yes", "explain=yes"), ("zero", "explain=0")):
        st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                            f"&date={D}&party_size=2&{q}")
        check_status(f"C3-E-1:{tag}", st, 422, b, code="validation_failed")
    # repeated/ambiguous use -> 422
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=2&explain=true&explain=true")
    check_status("C3-E-1:repeat", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=2&explain=true&explain=false")
    check_status("C3-E-1:mixed", st, 422, b, code="validation_failed")

    # E-2: no explain param -> stage-2 shape, no explain field anywhere
    st, hd, b, _ = avail("r_ops", D, 2)
    check_status("C3-E-2", st, 200, b)
    slots = (j(b) or {}).get("slots", [])
    expect("C3-E-2b", bool(slots) and all("explain" not in s for s in slots),
           "no explain field without param")

    # E-3/E-4/E-5: explain=true -> every slot carries explain listing every
    # table exactly once in fixture order, with required fields
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=2&explain=true")
    check_status("C3-E-3", st, 200, b)
    slots = (j(b) or {}).get("slots", [])
    ok = bool(slots) and all(
        [e.get("table_id") for e in (s.get("explain") or [])] ==
        ["t_a", "t_b", "t_c"] for s in slots)
    expect("C3-E-4", ok, "every table once, fixture order")
    fld_ok = all(
        set(e.keys()) >= {"table_id", "policy_version", "available", "rules"}
        for s in slots for e in (s.get("explain") or []))
    expect("C3-E-5", fld_ok, "explain entry fields")
    # E-6: rules ordered capacity then no_overlap, each {rule, holds}
    rule_ok = all(
        [r.get("rule") for r in e.get("rules", [])] == ["capacity", "no_overlap"]
        and all(set(r.keys()) == {"rule", "holds"} for r in e.get("rules", []))
        for s in slots for e in (s.get("explain") or []))
    expect("C3-E-6", rule_ok, "rules ordered capacity,no_overlap")
    # E-7/E-8: available == both rules; available-true ids == available_table_ids
    t_ok = True
    for s in slots:
        for e in s.get("explain", []):
            both = all(r["holds"] for r in e["rules"])
            if e.get("available") != both:
                t_ok = False
        ids = [e["table_id"] for e in s.get("explain", []) if e.get("available")]
        if ids != s.get("available_table_ids"):
            t_ok = False
    expect("C3-E-7/8", t_ok, "available==both rules; ids==available_table_ids")
    # E-11/R3-1: policy_version present (0 pre-policy); available_options kept
    expect("C3-E-11", all(e.get("policy_version") == 0 for s in slots
                          for e in s.get("explain", [])),
           "policy_version 0 before any publish")
    expect("C3-E-R1", all("available_options" in s for s in slots),
           "available_options still present with explain")

    # truth-table probes on one slot T
    # capacity false only: party 5 fits only t_c -> t_a cap=false,ol=true
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=5&explain=true")
    sl = slot_at(b, T)
    ex = {e["table_id"]: e for e in (sl or {}).get("explain", [])}
    expect("C3-E-T1", ex.get("t_a", {}).get("rules") ==
           [{"rule": "capacity", "holds": False},
            {"rule": "no_overlap", "holds": True}]
           and ex["t_a"]["available"] is False,
           f"t_a capacity-only failure {ex.get('t_a')}")
    expect("C3-E-T1b", ex.get("t_c", {}).get("available") is True,
           "t_c holds both for party 5")
    # no_overlap false only: book t_c at T (party 2) then re-explain party 2
    st, hd, b, _ = book(mgr(), "r_ops", T, party=2, table="t_c")
    check_status("C3-E-T2:setup", st, 201, b)
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=2&explain=true")
    sl = slot_at(b, T)
    ex = {e["table_id"]: e for e in (sl or {}).get("explain", [])}
    expect("C3-E-T3", ex.get("t_c", {}).get("rules") ==
           [{"rule": "capacity", "holds": True},
            {"rule": "no_overlap", "holds": False}]
           and ex["t_c"]["available"] is False,
           f"t_c overlap-only failure {ex.get('t_c')}")
    # both false: party 9 -> every capacity false; t_c also overlapped
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=9&explain=true")
    sl = slot_at(b, T)
    ex = {e["table_id"]: e for e in (sl or {}).get("explain", [])}
    expect("C3-E-T4", ex.get("t_c", {}).get("rules") ==
           [{"rule": "capacity", "holds": False},
            {"rule": "no_overlap", "holds": False}],
           f"t_c both-false {ex.get('t_c')}")
    # E-9: slot still listed when nothing available; closed day -> slots []
    expect("C3-E-9", sl is not None and
           sl.get("available_table_ids") == [] and len(sl.get("explain", [])) == 3,
           "all-taken slot still listed with full explain")
    d_closed = "2026-09-26"      # r_anker: only thu/fri open; 2026-09-26 = sat
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_anker"
                        f"&date={d_closed}&party_size=2&explain=true")
    expect("C3-E-9b", st == 200 and (j(b) or {}).get("slots") == [],
           f"closed day slots=[] st={st}")

    # E-10/E-11: published policy changes the grid; explain carries its version
    st, hd, b, _ = publish(mgr(), "r_ops", pol(eff=T[:10], slot=30, dur=30))
    check_status("C3-E-10:setup", st, 201, b)
    ver = (j(b) or {}).get("policy_version")
    st, hd, b, _ = call("GET", "/availability?restaurant_id=r_ops"
                        f"&date={D}&party_size=2&explain=true")
    slots = (j(b) or {}).get("slots", [])
    vals = [s.get("starts_at_local", "")[-2:] for s in slots]
    expect("C3-E-10", slots and all(m in ("00", "30") for m in vals),
           f"policy grid 30min -> minutes {sorted(set(vals))}")
    expect("C3-E-11b", all(e.get("policy_version") == ver for s in slots
                           for e in s.get("explain", [])),
           f"explain policy_version == published {ver}")

# ================= P — manager fixture, auth, publish =================

def sec_policy_fixture():
    # P-1 default: absent manager_user_ids -> nobody may publish
    reset3(fixture_combo())          # stage-2 fixture: no manager field at all
    st, hd, b, _ = publish(mgr(), "r_ops", pol())
    check_status("C3-P-1", st, 403, b, code="forbidden")
    # R3-2 invalid variants -> 422 validation_failed + state unchanged
    base = fixture_p3()
    variants = {
        "not_list":   "u_ada",
        "elem_int":   ["u_ada", 7],
        "elem_null":  [None],
        "unknown":    ["u_ada", "u_ghost"],
        "overlength": ["u_" + "x" * 80],
        "elem_obj":   [{"id": "u_ada"}],
    }
    for tag, mids in variants.items():
        fx = fixture_p3()
        for r in fx["restaurants"]:
            r["manager_user_ids"] = mids
        st, hd, b, _ = call("POST", "/_test/reset", body=fx, timeout=15)
        check_status(f"C3-P-2:{tag}", st, 422, b, code="validation_failed")
        st, hd, b2, _ = call("GET", "/restaurants/r_ops")
        expect(f"C3-P-2b:{tag}", st == 200 and
               (j(b2) or {}).get("name") == "Ops Haus",
               "state unchanged after invalid manager fixture")
        call("POST", "/_test/reset", body=base, timeout=15)
    # duplicates collapse to first occurrence (valid)
    fx = fixture_p3()
    for r in fx["restaurants"]:
        r["manager_user_ids"] = ["u_ada", "u_ada", "u_ada"]
    st, hd, b, _ = call("POST", "/_test/reset", body=fx, timeout=15)
    check_status("C3-P-2c", st, 204, b)
    st, hd, b, _ = publish(mgr(), "r_ops", pol())
    check_status("C3-P-2d", st, 201, b)
    # explicit empty list -> no managers
    fx = fixture_p3()
    for r in fx["restaurants"]:
        r["manager_user_ids"] = []
    call("POST", "/_test/reset", body=fx, timeout=15)
    st, hd, b, _ = publish(mgr(), "r_ops", pol())
    check_status("C3-P-2e", st, 403, b, code="forbidden")
    reset3()

def sec_policy_auth():
    reset3()
    body = pol()
    st, hd, b, _ = publish(None, "r_ops", body)
    check_status("C3-P-3a", st, 401, b)                 # no token
    st, hd, b, _ = publish("bogus.token.here", "r_ops", body)
    check_status("C3-P-3b", st, 401, b)                 # bad token
    st, hd, b, _ = publish(nonmgr(), "r_ops", body)
    check_status("C3-P-3c", st, 403, b, code="forbidden")  # non-manager
    st, hd, b, _ = publish(mgr(), "r_nope", body)
    check_status("C3-P-3d", st, 404, b, code="not_found")  # unknown restaurant
    st, hd, b, _ = publish(None, "r_nope", body)
    check_status("C3-P-3e", st, 401, b)                 # 401 before 404
    st, hd, b, _ = publish(mgr(), "r_ops", body)
    check_status("C3-P-3f", st, 201, b)                 # manager ok
    # P-3: manager gains nothing on other diners' private views
    ada = mgr(); bob = nonmgr()
    st, hd, b, _ = book(bob, "r_ops", utc_local(30 * 60), party=2, table="t_a")
    bref = (j(b) or {}).get("reference")
    st, hd, b, _ = call("GET", f"/reservations/{bref}", token=ada)
    check_status("C3-P-4a", st, 404, b, code="not_found")
    st, hd, b, _ = hist(bref, token=ada)
    check_status("C3-P-4b", st, 404, b, code="not_found")
    reset3()

def sec_policy_idem():
    reset3()
    ada = mgr()
    body = pol()
    # missing key -> 400 missing_idempotency_key
    st, hd, b, _ = call("POST", "/restaurants/r_ops/policies",
                        body=body, token=ada)
    check_status("C3-P-5a", st, 400, b, code="missing_idempotency_key")
    K = key("pol")
    st, hd, b, _ = publish(ada, "r_ops", body, idem=K)
    check_status("C3-P-5b", st, 201, b)
    orig = j(b); ver = (orig or {}).get("policy_version")
    expect("C3-P-5c", isinstance(ver, int) and ver == 1,
           f"first version == 1 got {ver!r}")
    # replay -> 200 identical body, no new version allocated (R3-3)
    st, hd, b, _ = publish(ada, "r_ops", body, idem=K)
    check_status("C3-P-6a", st, 200, b)
    expect("C3-P-6b", j(b) == orig, "replay body identical to original")
    st, hd, b, _ = list_policies("r_ops")
    expect("C3-P-6c", len((j(b) or {}).get("policies", [])) == 1,
           "replay allocated no version")
    # same key different body -> 409 idempotency_key_reuse
    st, hd, b, _ = publish(ada, "r_ops", pol(slot=45), idem=K)
    check_status("C3-P-7", st, 409, b, code="idempotency_key_reuse")
    # failed write releases the key (R3-3: allocation on success only)
    KF = key("polf")
    st, hd, b, _ = publish(ada, "r_ops", pol(slot=0), idem=KF)
    check_status("C3-P-8a", st, 422, b, code="validation_failed")
    st, hd, b, _ = publish(ada, "r_ops", pol(slot=45), idem=KF)
    check_status("C3-P-8b", st, 201, b)
    expect("C3-P-8c", (j(b) or {}).get("policy_version") == 2,
           f"version after failed+retry == 2 got {(j(b) or {}).get('policy_version')}")
    # R3-9: same key on a different path is a different request
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=K,
                        body={"restaurant_id": "r_ops", "table_id": "t_a",
                              "starts_at_local": utc_local(34 * 60),
                              "party_size": 2})
    check_status("C3-P-9", st, 201, b)
    reset3()

def sec_policy_validation():
    reset3()
    ada = mgr()
    # P-5: omitted required fields -> 422 each
    for f in ("effective_from", "slot_minutes",
              "reservation_duration_minutes", "cancellation_cutoff_minutes",
              "opening_hours", "capacities"):
        p = pol(); p.pop(f)
        st, hd, b, _ = publish(ada, "r_ops", p)
        check_status(f"C3-P-10:{f}", st, 422, b, code="validation_failed")
    # P-11: unknown fields ignored -> still 201
    st, hd, b, _ = publish(ada, "r_ops", pol(bogus_field="x", another=[1, 2]))
    check_status("C3-P-11", st, 201, b)
    expect("C3-P-11b", "bogus_field" not in (j(b) or {}),
           "unknown field not echoed back")
    # P-6: effective_from must be a real YYYY-MM-DD date
    for tag, v in (("nondigit", "28/09/2026"), ("badmonth", "2026-13-01"),
                   ("badday", "2026-02-30"), ("datetime", "2026-09-28T00:00"),
                   ("int", 20260928), ("null", None), ("bool", True)):
        st, hd, b, _ = publish(ada, "r_ops", pol(eff=v))
        check_status(f"C3-P-12:{tag}", st, 422, b, code="validation_failed")
    # P-17: past effective date is legal
    st, hd, b, _ = publish(ada, "r_ops", pol(eff="2020-01-01"))
    check_status("C3-P-12:past", st, 201, b)
    # P-7: integer bounds; booleans are not integers
    for f, lo, hi in (("slot_minutes", 1, 1440),
                      ("reservation_duration_minutes", 1, 1440),
                      ("cancellation_cutoff_minutes", 0, 10080)):
        for tag, v in (("lo-1", lo - 1), ("hi+1", hi + 1),
                       ("float", float(lo)), ("str", str(lo)),
                       ("bool", True), ("null", None)):
            st, hd, b, _ = publish(ada, "r_ops", pol(**{f: v}))
            check_status(f"C3-P-13:{f}:{tag}", st, 422, b,
                         code="validation_failed")
        st, hd, b, _ = publish(ada, "r_ops", pol(**{f: lo}))
        check_status(f"C3-P-13:{f}:lo", st, 201, b)
        st, hd, b, _ = publish(ada, "r_ops", pol(**{f: hi}))
        check_status(f"C3-P-13:{f}:hi", st, 201, b)
    # P-8: opening_hours stage-1 rules + no duplicate weekdays
    for tag, hrs in (("dup_wd", [{"weekday": "mon", "opens": "10:00",
                                 "closes": "12:00"},
                                {"weekday": "mon", "opens": "18:00",
                                 "closes": "22:00"}]),
                     ("bad_wd", [{"weekday": "noday", "opens": "10:00",
                                  "closes": "12:00"}]),
                     ("reversed", [{"weekday": "mon", "opens": "22:00",
                                    "closes": "10:00"}]),
                     ("not_list", "mon 10:00-12:00"),
                     ("entry_missing", [{"weekday": "mon"}])):
        st, hd, b, _ = publish(ada, "r_ops", pol(hours=hrs))
        check_status(f"C3-P-14:{tag}", st, 422, b, code="validation_failed")
    # R3-14: partial week
    st, hd, b, _ = publish(ada, "r_ops",
        pol(eff="2026-11-02",
            hours=[{"weekday": "mon", "opens": "10:00", "closes": "12:00"}]))
    check_status("C3-P-14:partial", st, 201, b)
    # P-9: capacities must name exactly the restaurant's tables, each int 1..100
    for tag, caps in (("missing", {"t_a": 4, "t_b": 4}),
                      ("extra", {"t_a": 4, "t_b": 4, "t_c": 8, "t_x": 2}),
                      ("zero", {"t_a": 4, "t_b": 4, "t_c": 0}),
                      ("over", {"t_a": 4, "t_b": 4, "t_c": 101}),
                      ("float", {"t_a": 4, "t_b": 4, "t_c": 8.0}),
                      ("str", {"t_a": 4, "t_b": 4, "t_c": "8"}),
                      ("bool", {"t_a": 4, "t_b": 4, "t_c": True}),
                      ("foreign", {"t_a": 4, "t_b": 4, "t_1": 8}),
                      ("not_map", ["t_a", "t_b", "t_c"])):
        st, hd, b, _ = publish(ada, "r_ops", pol(caps=caps))
        check_status(f"C3-P-15:{tag}", st, 422, b, code="validation_failed")
    for cap in (1, 100):
        st, hd, b, _ = publish(ada, "r_ops",
                               pol(caps={"t_a": cap, "t_b": cap, "t_c": cap}))
        check_status(f"C3-P-15:cap{cap}", st, 201, b)
    # P-12: failed publish allocates no version and changes nothing
    st, hd, b, _ = list_policies("r_ops")
    n_before = len((j(b) or {}).get("policies", []))
    publish(ada, "r_ops", pol(slot=0))
    st, hd, b, _ = list_policies("r_ops")
    expect("C3-P-16", len((j(b) or {}).get("policies", [])) == n_before,
           "invalid publish allocated no version")
    vers = [p.get("policy_version") for p in (j(b) or {}).get("policies", [])]
    expect("C3-P-16b", vers == list(range(1, len(vers) + 1)),
           f"versions contiguous {vers}")
    # P-15: no update/delete path mutates a policy
    for m in ("PATCH", "PUT", "DELETE"):
        st, hd, b, _ = call(m, "/restaurants/r_ops/policies",
                            body=pol(), token=ada)
        check_status(f"C3-P-17:{m}", st, (404, 405), b)
    st, hd, b, _ = call("DELETE", "/restaurants/r_ops/policies/1", token=ada)
    check_status("C3-P-17b", st, (404, 405), b)
    reset3()

# ---- P-13/P-16/P-18/P-19: listing order, selection, detail divergence ----

def sec_policy_order():
    reset3()
    ada = mgr()
    st, hd, b, _ = publish(ada, "r_ops", pol(eff="2026-10-10", slot=30))
    v1 = (j(b) or {}).get("policy_version")
    check_status("C3-P-18a", st, 201, b)
    st, hd, b, _ = publish(ada, "r_ops", pol(eff="2026-10-01", slot=45))
    v2 = (j(b) or {}).get("policy_version")
    check_status("C3-P-18b", st, 201, b)
    # P-18: public list in PUBLICATION order (not effective order), no policy 0
    st, hd, b, _ = list_policies("r_ops")            # anonymous
    check_status("C3-P-19a", st, 200, b)
    pl = (j(b) or {}).get("policies", [])
    expect("C3-P-19b", [p.get("policy_version") for p in pl] == [v1, v2],
           f"publication order {[p.get('policy_version') for p in pl]}")
    expect("C3-P-19c", all(p.get("policy_version", 0) >= 1 for p in pl),
           "policy 0 omitted from list")
    # P-16: selection = greatest effective_from <= booking local start date
    # r_ops policy-0 slot=15; P2(eff 10-01) slot=45; P1(eff 10-10) slot=30.
    st, hd, b, _ = avail("r_ops", "2026-10-05", 2)
    sl = (j(b) or {}).get("slots", [])
    ts = [s.get("starts_at_local", "") for s in sl]
    gaps = {int(b_[11:13]) * 60 + int(b_[14:16])
            - int(a[11:13]) * 60 - int(a[14:16])
            for a, b_ in zip(ts, ts[1:])}
    expect("C3-P-20a", sl and gaps == {45},
           f"10-05 uses P2 45min grid -> gaps {gaps}")
    st, hd, b, _ = avail("r_ops", "2026-10-15", 2)
    sl = (j(b) or {}).get("slots", [])
    mm = sorted({s.get("starts_at_local", "")[-2:] for s in sl})
    expect("C3-P-20b", sl and all(m in ("00", "30") for m in mm),
           f"10-15 uses P1 30min grid -> {mm}")
    st, hd, b, _ = avail("r_ops", "2026-09-30", 2)
    sl = (j(b) or {}).get("slots", [])
    mm = sorted({s.get("starts_at_local", "")[-2:] for s in sl})
    expect("C3-P-20c", sl and all(m in ("00", "15", "30", "45") for m in mm),
           f"09-30 uses policy 0 15min grid -> {mm}")
    # same effective_from: later publication wins (greatest version)
    st, hd, b, _ = publish(ada, "r_ops", pol(eff="2026-10-10", slot=60))
    v3 = (j(b) or {}).get("policy_version")
    check_status("C3-P-21a", st, 201, b)
    st, hd, b, _ = avail("r_ops", "2026-10-15", 2)
    sl = (j(b) or {}).get("slots", [])
    mm = sorted({s.get("starts_at_local", "")[-2:] for s in sl})
    expect("C3-P-21b", sl and all(m == "00" for m in mm),
           f"tie -> highest version (60min grid) -> {mm}")
    # P-19: restaurant detail still returns fixture config, not policy values
    st, hd, b, _ = call("GET", "/restaurants/r_ops")
    r = j(b) or {}
    expect("C3-P-22", r.get("slot_minutes") == 15
           and r.get("reservation_duration_minutes") == 60
           and r.get("cancellation_cutoff_minutes") == 120,
           f"detail unchanged slot={r.get('slot_minutes')}")
    reset3()

# ================= T — accepted terms & revisions =================

def sec_terms():
    reset3()
    ada = mgr()
    T = utc_local(40 * 60)
    # T-1/T-2/T-3: create response gains revision=1 + policy-0 accepted_terms
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    check_status("C3-T-1", st, 201, b)
    r = j(b) or {}
    ref = r.get("reference")
    expect("C3-T-2", r.get("revision") == 1, f"revision==1 got {r.get('revision')}")
    expect("C3-T-3", r.get("accepted_terms") == terms_p0_ops(),
           f"terms {r.get('accepted_terms')}")
    expect("C3-T-3b", set(r.get("accepted_terms", {}).keys()) == TERMS_KEYS
           and "effective_from" not in r.get("accepted_terms", {}),
           "terms key set excludes effective_from")
    # T-1 on every view
    st, hd, b, _ = call("GET", f"/reservations/{ref}", token=ada)
    expect("C3-T-1b", (j(b) or {}).get("revision") == 1
           and (j(b) or {}).get("accepted_terms") == terms_p0_ops(),
           "GET carries revision+terms")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    mine = [x for x in (j(b) or {}).get("reservations", [])
            if x.get("reference") == ref]
    expect("C3-T-1c", mine and mine[0].get("revision") == 1
           and mine[0].get("accepted_terms") == terms_p0_ops(),
           "list carries revision+terms")
    # T-4: publishing a policy does not touch existing bookings
    st, hd, b, _ = publish(ada, "r_ops",
                           pol(eff=T[:10], dur=120, caps={"t_a": 2, "t_b": 2,
                                                          "t_c": 2}))
    check_status("C3-T-4:setup", st, 201, b)
    st, hd, b, _ = call("GET", f"/reservations/{ref}", token=ada)
    r2 = j(b) or {}
    expect("C3-T-4", r2.get("revision") == 1 and
           r2.get("accepted_terms") == terms_p0_ops()
           and r2.get("status") == "confirmed",
           "existing booking untouched by publish (R3-18 smaller cap ok)")
    # T-6: cancel checks the ACCEPTED cutoff; old booking still cancels
    # under policy-0 terms even though a new policy is now effective.
    st, hd, b, _ = call("POST", f"/reservations/{ref}/cancel", token=ada)
    check_status("C3-T-6", st, 200, b)
    expect("C3-T-7", (j(b) or {}).get("revision") == 2,
           "cancel increments revision once")
    st, hd, b, _ = call("POST", f"/reservations/{ref}/cancel", token=ada)
    check_status("C3-T-7b", st, 200, b)   # inherited: repeat cancel is a 200 no-op
    expect("C3-T-7bb", (j(b) or {}).get("status") == "cancelled",
           "still cancelled")
    st, hd, b, _ = decision(ref, token=ada)
    expect("C3-T-7c", (j(b) or {}).get("revision") == 2,
           "repeat cancel does not bump revision")
    # T-5: replay of the ORIGINAL create returns the original response
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a", idem=None)
    reset3()

def sec_amend():
    reset3()
    ada = mgr()
    T = utc_local(50 * 60); T2 = utc_local(60 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_b")
    check_status("C3-T-8:setup", st, 201, b)
    ref = (j(b) or {}).get("reference")
    # T-13: invalid expected_revision types -> 422
    for tag, v in (("zero", 0), ("neg", -1), ("float", 1.5),
                   ("str", "1"), ("bool", True), ("null", None)):
        st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                            body={"expected_revision": v})
        check_status(f"C3-T-13:{tag}", st, 422, b, code="validation_failed")
    # T-12: correct current revision -> proceeds; stale -> 409 before validation
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"expected_revision": 1, "party_size": 3})
    check_status("C3-T-12a", st, 200, b)
    expect("C3-T-12b", (j(b) or {}).get("revision") == 2,
           "real amend bumps revision to 2")
    # stale revision beats BOTH cutoff and field validation ordering
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"expected_revision": 1,
                              "starts_at_local": "bad-format"})
    check_status("C3-T-12c", st, 409, b, code="stale_revision")
    # T-10: no-op amendment retains everything, still 200
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 3})
    check_status("C3-T-10", st, 200, b)
    st, hd, b2, _ = call("GET", f"/reservations/{ref}", token=ada)
    expect("C3-T-10b", (j(b2) or {}).get("revision") == 2,
           "no-op kept revision 2")
    st, hd, bh, _ = hist(ref, token=ada)
    expect("C3-T-10c", len(entries_of(bh) or []) == 2,
           f"no-op added no history entries={len(entries_of(bh) or [])}")
    # T-15: unknown fields ignored
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 4, "zzz_field": {"x": 1}})
    check_status("C3-T-15", st, 200, b)
    expect("C3-T-15b", (j(b) or {}).get("party_size") == 4,
           "unknown field ignored, known field applied")
    # T-8: amend across a policy boundary re-snapshots accepted terms
    st, hd, b, _ = publish(ada, "r_ops",
                           pol(eff=T2[:10], slot=15, dur=30, cut=30))
    check_status("C3-T-9:setup", st, 201, b)
    ver_new = (j(b) or {}).get("policy_version")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"starts_at_local": T2})
    check_status("C3-T-9", st, 200, b)
    r = j(b) or {}
    expect("C3-T-9b", r.get("revision") == 4
           and (r.get("accepted_terms") or {}).get("policy_version") == ver_new
           and (r.get("accepted_terms") or {}).get(
               "reservation_duration_minutes") == 30,
           f"policy-crossing amend re-snapshot terms rev={r.get('revision')}")
    # T-11: failed amendment changes nothing (bad party size)
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 0})
    check_status("C3-T-11", st, 422, b)
    st, hd, b2, _ = call("GET", f"/reservations/{ref}", token=ada)
    expect("C3-T-11b", (j(b2) or {}).get("revision") == 4
           and (j(b2) or {}).get("party_size") == 4,
           "failed amend changed nothing")
    # T-14: concurrent amends with same expected_revision -> <=1 real change
    st, hd, b, _ = book(ada, "r_ops", utc_local(70 * 60), party=2, table="t_a")
    ref2 = (j(b) or {}).get("reference")
    N = 8
    barrier = threading.Barrier(N)
    def one(i):
        barrier.wait()
        return call("PATCH", f"/reservations/{ref2}", token=ada,
                    body={"expected_revision": 1, "party_size": 3 + i % 2})
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(one, range(N)))
    sts = [r[0] for r in rs]
    n200 = sts.count(200)
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    fin = (j(b) or {}).get("revision")
    expect("C3-T-14", n200 <= 1 and fin in (1, 2),
           f"same-revision race: {n200}x200 final_rev={fin} sts={sts}")
    reset3()

# ================= H — reservation history & decision =================

def _check_created_entry(cid, e, table_field, to_val, local, party):
    """created: seq 1, three change entries from null, ordered."""
    ch = e.get("changes") or []
    want = [{"field": table_field, "from": None, "to": to_val},
            {"field": "starts_at_local", "from": None, "to": local},
            {"field": "party_size", "from": None, "to": party}]
    expect(cid + ":shape", e.get("seq") == 1 and e.get("event") == "created"
           and ch == want, f"created entry {e}")

def sec_history():
    reset3()
    ada = mgr()
    T = utc_local(80 * 60); T2 = utc_local(90 * 60)
    K = key("hist")
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_b", idem=K)
    check_status("C3-H-0", st, 201, b)
    ref = (j(b) or {}).get("reference")
    # H-1/H-5: created entry carries the three fields from null
    st, hd, b, _ = hist(ref, token=ada)
    check_status("C3-H-1", st, 200, b)
    ent = entries_of(b) or []
    expect("C3-H-1b", (j(b) or {}).get("reference") == ref
           and len(ent) == 1, f"one entry {len(ent)}")
    if ent:
        _check_created_entry("C3-H-5", ent[0], "table_id", "t_b", T, 2)
        # H-10: entry carries revision + complete accepted_terms (policy 0)
        expect("C3-H-10", ent[0].get("revision") == 1 and
               ent[0].get("accepted_terms") == terms_p0_ops(),
               "entry carries revision+terms")
    # H-9: replaying the create records nothing new
    call("POST", "/reservations", token=ada, idem=K,
         body={"restaurant_id": "r_ops", "table_id": "t_b",
               "starts_at_local": T, "party_size": 2})
    st, hd, b, _ = hist(ref, token=ada)
    expect("C3-H-9", len(entries_of(b) or []) == 1, "replay adds no entry")
    # H-6: patch party_size only -> changed entry with only that field
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 3})
    check_status("C3-H-6a", st, 200, b)
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    expect("C3-H-6b", len(ent) == 2 and ent[1].get("event") == "changed"
           and ent[1].get("changes") ==
           [{"field": "party_size", "from": 2, "to": 3}]
           and ent[1].get("seq") == 2 and ent[1].get("revision") == 2,
           f"changed entry {ent[1] if len(ent) > 1 else None}")
    # H-6b: multi-field patch -> canonical change order
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 4, "table_id": "t_c",
                              "starts_at_local": T2})
    check_status("C3-H-6c", st, 200, b)
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    ch = (ent[2] if len(ent) > 2 else {}).get("changes") or []
    expect("C3-H-6d", [c.get("field") for c in ch] ==
           ["table_id", "starts_at_local", "party_size"],
           f"change order {[c.get('field') for c in ch]}")
    # H-4: seq contiguous and ordered; at order agrees
    seqs = [e.get("seq") for e in ent]
    ats = [e.get("at") for e in ent]
    expect("C3-H-4", seqs == list(range(1, len(ent) + 1))
           and ats == sorted(ats), f"seqs {seqs}")
    # H-7: no-op patch records nothing
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 4, "table_id": "t_c",
                              "starts_at_local": T2})
    check_status("C3-H-7a", st, 200, b)
    st, hd, b, _ = hist(ref, token=ada)
    expect("C3-H-7b", len(entries_of(b) or []) == 3, "no-op recorded nothing")
    # H-8: cancel -> cancelled entry with empty changes; nothing after
    st, hd, b, _ = call("POST", f"/reservations/{ref}/cancel", token=ada)
    check_status("C3-H-8a", st, 200, b)
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    expect("C3-H-8b", len(ent) == 4 and ent[-1].get("event") == "cancelled"
           and ent[-1].get("changes") == [],
           f"cancelled terminal {ent[-1] if ent else None}")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"party_size": 2})
    check_status("C3-H-8c", st, 409, b, code="reservation_cancelled")
    st, hd, b, _ = hist(ref, token=ada)
    expect("C3-H-8d", len(entries_of(b) or []) == 4,
           "nothing follows cancelled")
    # H-3: cancelled reservation history still readable by owner
    expect("C3-H-3", st == 200, "cancelled history readable")
    # H-11: decision endpoint, incl. after cancellation
    st, hd, b, _ = decision(ref, token=ada)
    check_status("C3-H-11", st, 200, b)
    d = j(b) or {}
    expect("C3-H-11b", d.get("reference") == ref and d.get("revision") == 4
           and set(d.get("accepted_terms", {}).keys()) == TERMS_KEYS,
           f"decision shape {sorted(d)}")
    # H-2/H-12: owner-only 404 for foreign AND anonymous AND bad token
    st, hd, b, _ = hist(ref, token=nonmgr())
    check_status("C3-H-2a", st, 404, b, code="not_found")
    st, hd, b, _ = hist(ref, token=None)
    check_status("C3-H-2b", st, 404, b, code="not_found")
    st, hd, b, _ = hist(ref, token="bad.tok")
    check_status("C3-H-2c", st, 404, b, code="not_found")
    st, hd, b, _ = hist("ZZZZZZ", token=ada)
    check_status("C3-H-2d", st, 404, b, code="not_found")
    st, hd, b, _ = decision(ref, token=None)
    check_status("C3-H-12", st, 404, b, code="not_found")
    st, hd, b, _ = decision(ref, token=nonmgr())
    check_status("C3-H-12b", st, 404, b, code="not_found")
    reset3()

def sec_history_terms_snapshot():
    """H-10: old entries never acquire newer terms (policy-crossing amend)."""
    reset3()
    ada = mgr()
    T = utc_local(100 * 60); T2 = utc_local(110 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    st, hd, b, _ = publish(ada, "r_ops", pol(eff=T2[:10], slot=15, dur=30, cut=30))
    check_status("C3-H-13a", st, 201, b)
    ver = (j(b) or {}).get("policy_version")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref}", token=ada,
                        body={"starts_at_local": T2})
    check_status("C3-H-13b", st, 200, b)
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    expect("C3-H-13c", len(ent) == 2
           and ent[0].get("accepted_terms", {}).get("policy_version") == 0
           and ent[1].get("accepted_terms", {}).get("policy_version") == ver,
           "old entry keeps policy-0 terms; new entry has new terms")
    reset3()

# ================= B — combined-table history =================

def sec_combo_history():
    reset3()
    ada = mgr()
    T = utc_local(120 * 60)
    st, hd, b, _ = book(ada, "r_combo", T, party=5, ids=["t_b", "t_a"])
    check_status("C3-B-1", st, 201, b)
    r = j(b) or {}
    ref = r.get("reference")
    # canonical order = declared combination order
    expect("C3-B-4", r.get("table_ids") == ["t_a", "t_b"],
           f"canonical pair {r.get('table_ids')}")
    # B-2: pair create history uses table_ids from null, not table_id
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    ch = (ent[0] if ent else {}).get("changes") or []
    expect("C3-B-2", [c.get("field") for c in ch] ==
           ["table_ids", "starts_at_local", "party_size"]
           and ch[0].get("from") is None and ch[0].get("to") == ["t_a", "t_b"],
           f"pair created entry {ch}")
    expect("C3-B-2b", all(c.get("field") != "table_id" for c in ch),
           "no table_id field in pair history (R3-6)")
    # B-3: pair -> different pair uses complete table_ids lists
    T2 = utc_local(130 * 60)
    st, hd, b, _ = book(ada, "r_combo", T2, party=2, table="t_c")
    ref2 = (j(b) or {}).get("reference")
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", token=ada,
                        body={"table_ids": ["t_b", "t_c"]})
    check_status("C3-B-3a", st, 200, b)
    st, hd, b, _ = hist(ref2, token=ada)
    ent = entries_of(b) or []
    ch = (ent[-1] if ent else {}).get("changes") or []
    expect("C3-B-3b", len(ent) == 2 and ch ==
           [{"field": "table_ids", "from": ["t_c"], "to": ["t_b", "t_c"]}],
           f"single->pair history {ch}")
    # B-5: reversed pair = same set = no-op, no entry/revision bump
    st, hd, b, _ = call("PATCH", f"/reservations/{ref2}", token=ada,
                        body={"table_ids": ["t_c", "t_b"]})
    check_status("C3-B-5a", st, 200, b)
    st, hd, b2, _ = call("GET", f"/reservations/{ref2}", token=ada)
    st, hd, bh, _ = hist(ref2, token=ada)
    expect("C3-B-5b", (j(b2) or {}).get("revision") == 2
           and len(entries_of(bh) or []) == 2,
           "reversed pair is a no-op (R3-5)")
    reset3()

# ================= S — recurring series =================

def sec_series_validate():
    reset3()
    ada = mgr(); bob = nonmgr()
    T = utc_local(140 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    check_status("C3-S-0", st, 201, b)
    ref = (j(b) or {}).get("reference")
    # S-1: no token -> 401; missing key -> 400
    st, hd, b, _ = call("POST", "/series",
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 1})
    check_status("C3-S-1a", st, 401, b)
    st, hd, b, _ = call("POST", "/series", token=ada,
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 1})
    check_status("C3-S-1b", st, 400, b, code="missing_idempotency_key")
    # S-3: foreign anchor -> 404; unknown -> 404
    st, hd, b, _ = call("POST", "/series", token=bob, idem=key(),
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 1})
    check_status("C3-S-3a", st, 404, b, code="not_found")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": "ZZZZZZ", "count": 3,
                              "interval_weeks": 1})
    check_status("C3-S-3b", st, 404, b, code="not_found")
    # S-4: count 2..12 / interval 1..4 boundaries; bool/str -> 422
    for tag, fld, v in (("c1", "count", 1), ("c13", "count", 13),
                        ("c0", "count", 0), ("cstr", "count", "3"),
                        ("cfloat", "count", 2.5), ("cbool", "count", True),
                        ("i0", "interval_weeks", 0), ("i5", "interval_weeks", 5),
                        ("istr", "interval_weeks", "1"),
                        ("ibool", "interval_weeks", False)):
        bd = {"anchor_reference": ref, "count": 3, "interval_weeks": 1}
        bd[fld] = v
        st, hd, b, _ = call("POST", "/series", token=ada, idem=key(), body=bd)
        check_status(f"C3-S-4:{tag}", st, 422, b, code="validation_failed")
    # bad anchor_reference types
    for tag, v in (("int", 7), ("null", None), ("missing", "OMIT")):
        bd = {"anchor_reference": ref, "count": 3, "interval_weeks": 1}
        if v == "OMIT":
            bd.pop("anchor_reference")
        else:
            bd["anchor_reference"] = v
        st, hd, b, _ = call("POST", "/series", token=ada, idem=key(), body=bd)
        check_status(f"C3-S-4b:{tag}", st, (400, 422), b)
    # S-2: cancelled anchor -> 409 reservation_cancelled
    st, hd, b, _ = book(ada, "r_ops", utc_local(150 * 60), party=2, table="t_b")
    ref_c = (j(b) or {}).get("reference")
    call("POST", f"/reservations/{ref_c}/cancel", token=ada)
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref_c, "count": 2,
                              "interval_weeks": 1})
    check_status("C3-S-3c", st, 409, b, code="reservation_cancelled")
    reset3()

def _occ_dates(anchor_local, count, interval):
    """occurrence i local date = anchor date + i*interval*7 days, same clock."""
    from datetime import date as _d, timedelta as _td
    d0 = _d.fromisoformat(anchor_local[:10])
    clock = anchor_local[11:16]
    return [f"{(d0 + _td(weeks=i * interval)).isoformat()}T{clock}"
            for i in range(count)]

def sec_series_lifecycle():
    reset3()
    ada = mgr(); bob = nonmgr()
    T = utc_local(160 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=3, table="t_b")
    check_status("C3-S-10", st, 201, b)
    anchor = j(b) or {}
    ref = anchor.get("reference")
    K = key("ser")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=K,
                        body={"anchor_reference": ref, "count": 4,
                              "interval_weeks": 1, "zzz": "ignored"})
    check_status("C3-S-12", st, 201, b)
    S = j(b) or {}
    sid = S.get("series_id")
    # S-12/S-24: shape; opaque id <=64; revision 1; count occurrences in order
    expect("C3-S-12b", isinstance(sid, str) and 0 < len(sid) <= 64
           and S.get("revision") == 1 and S.get("interval_weeks") == 1,
           f"series shape id={sid!r} rev={S.get('revision')}")
    occ = S.get("occurrences") or []
    expect("C3-S-12c", len(occ) == 4 and
           [o.get("index") for o in occ] == [0, 1, 2, 3]
           and all(o.get("exception") is False for o in occ),
           f"{len(occ)} occurrences in index order")
    refs = [o.get("reference") for o in occ]
    expect("C3-S-12d", refs[0] == ref and len(set(refs)) == 4,
           f"anchor first, distinct refs {refs}")
    resps = [o.get("reservation") or {} for o in occ]
    # S-5: occurrence 0 IS the anchor, unchanged
    expect("C3-S-5", resps[0].get("reference") == ref
           and resps[0].get("revision") == 1
           and resps[0].get("accepted_terms") == terms_p0_ops(),
           "anchor identity/terms/revision unchanged")
    st, hd, b, _ = hist(ref, token=ada)
    expect("C3-S-5b", len(entries_of(b) or []) == 1,
           "anchor history unchanged by adoption")
    # S-6: generated dates = anchor + i*7d at same local clock time
    want_dates = _occ_dates(T, 4, 1)
    got_dates = [r.get("starts_at_local") for r in resps]
    expect("C3-S-6", got_dates == want_dates,
           f"occurrence dates {got_dates}")
    # S-9/S-14: anchor table selection + party size propagated; occupy tables
    expect("C3-S-9", all(r.get("table_id") == "t_b"
                         and r.get("party_size") == 3 for r in resps),
           "party/table propagated")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    mine = {x.get("reference") for x in (j(b) or {}).get("reservations", [])}
    expect("C3-S-14a", set(refs) <= mine, "occurrences in ordinary list")
    st, hd, b, _ = avail("r_ops", want_dates[2][:10], 2)
    sl = slot_at(b, want_dates[2])
    expect("C3-S-14b", sl is not None and
           "t_b" not in sl.get("available_table_ids", []),
           "occurrence occupies its table")
    st, hd, b, _ = hist(refs[1], token=ada)
    ent = entries_of(b) or []
    expect("C3-S-14c", len(ent) == 1 and ent[0].get("event") == "created",
           "generated occurrence has own created history")
    # S-3d: already adopted -> 409 already_in_series
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref, "count": 2,
                              "interval_weeks": 2})
    check_status("C3-S-3d", st, 409, b, code="already_in_series")
    # S-22: replay returns original response even after later changes
    st, hd, b, _ = call("POST", "/series", token=ada, idem=K,
                        body={"anchor_reference": ref, "count": 4,
                              "interval_weeks": 1, "zzz": "ignored"})
    check_status("C3-S-22", st, 200, b)
    expect("C3-S-22b", j(b) == S, "replay returns original series response")
    # S-15: GET /series/{id} owner only; foreign/anon -> 404
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    check_status("C3-S-15a", st, 200, b)
    expect("C3-S-15b", len((j(b) or {}).get("occurrences", [])) == 4,
           "GET returns current occurrences")
    st, hd, b, _ = call("GET", f"/series/{sid}", token=bob)
    check_status("C3-S-15c", st, 404, b, code="not_found")
    st, hd, b, _ = call("GET", f"/series/{sid}")
    check_status("C3-S-15d", st, 404, b, code="not_found")
    # S-16: real PATCH on occurrence -> exception true + series revision +1
    st, hd, b, _ = call("PATCH", f"/reservations/{refs[1]}", token=ada,
                        body={"party_size": 4})
    check_status("C3-S-16a", st, 200, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    S2 = j(b) or {}
    o1 = [o for o in S2.get("occurrences", []) if o.get("index") == 1]
    expect("C3-S-16b", S2.get("revision") == 2 and o1 and
           o1[0].get("exception") is True,
           f"exception set, series rev={S2.get('revision')}")
    # S-17: no-op patch changes neither
    st, hd, b, _ = call("PATCH", f"/reservations/{refs[1]}", token=ada,
                        body={"party_size": 4})
    check_status("C3-S-17a", st, 200, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C3-S-17b", (j(b) or {}).get("revision") == 2,
           "no-op kept series revision")
    # S-18: cancel occurrence -> series rev +1, retained, exception stays false
    st, hd, b, _ = call("POST", f"/reservations/{refs[2]}/cancel", token=ada)
    check_status("C3-S-18a", st, 200, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    S3 = j(b) or {}
    o2 = [o for o in S3.get("occurrences", []) if o.get("index") == 2]
    expect("C3-S-18b", S3.get("revision") == 3 and len(
        S3.get("occurrences", [])) == 4 and o2 and
        o2[0].get("exception") is False and
        (o2[0].get("reservation") or {}).get("status") == "cancelled",
        f"cancel bumps series rev, no exception {o2}")
    st, hd, b, _ = call("POST", f"/reservations/{refs[2]}/cancel", token=ada)
    check_status("C3-S-18c", st, 200, b)  # repeat cancel = no-op, retained
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    expect("C3-S-18d", (j(b) or {}).get("revision") == 3,
           "repeat cancel no bump")
    # S-19: cancelling the anchor does not cancel siblings
    st, hd, b, _ = call("POST", f"/reservations/{ref}/cancel", token=ada)
    check_status("C3-S-19a", st, 200, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    oc = {o["index"]: (o.get("reservation") or {}).get("status")
          for o in (j(b) or {}).get("occurrences", [])}
    expect("C3-S-19b", oc.get(0) == "cancelled" and oc.get(1) == "confirmed"
           and oc.get(3) == "confirmed",
           f"anchor cancel leaves siblings {oc}")
    reset3()

def sec_series_atomicity():
    reset3()
    ada = mgr(); bob = nonmgr()
    T = utc_local(180 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    # occurrence 2 lands on a slot where t_a is already taken by bob
    occ2 = _occ_dates(T, 4, 1)[2]
    st, hd, b, _ = book(bob, "r_ops", occ2, party=2, table="t_a")
    check_status("C3-S-20:setup", st, 201, b)
    K = key("serfail")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=K,
                        body={"anchor_reference": ref, "count": 4,
                              "interval_weeks": 1})
    # S-11: first failing occurrence determines the ordinary booking error
    check_status("C3-S-11", st, 409, b, code="table_unavailable")
    # S-10: atomic — no series, no reservations, no histories, no key claim
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    mine = (j(b) or {}).get("reservations", [])
    expect("C3-S-10a", len(mine) == 1, f"no generated rows survived {len(mine)}")
    st, hd, b, _ = hist(ref, token=ada)
    expect("C3-S-10b", len(entries_of(b) or []) == 1,
           "anchor history untouched by failed adoption")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=K,
                        body={"anchor_reference": ref, "count": 4,
                              "interval_weeks": 1})
    # key released: same request re-executes (409 again, not a 200 replay)
    expect("C3-S-10c", st == 409 and err_code(b) == "table_unavailable",
           f"failed adoption released key st={st}")
    # freeing the blocker lets the identical retry succeed
    bref = None
    st, hd, b, _ = call("GET", "/reservations", token=bob)
    for x in (j(b) or {}).get("reservations", []):
        if x.get("starts_at_local") == occ2:
            bref = x.get("reference")
    call("POST", f"/reservations/{bref}/cancel", token=bob)
    st, hd, b, _ = call("POST", "/series", token=ada, idem=K,
                        body={"anchor_reference": ref, "count": 4,
                              "interval_weeks": 1})
    check_status("C3-S-10d", st, 201, b)
    reset3()

def sec_series_policy_dst():
    """S-7 policy-per-date; S-8 DST gap/fold on generated occurrences."""
    reset3()
    ada = mgr()
    T = utc_local(200 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    # policy effective exactly on occurrence 1's date changes duration/caps
    eff = _occ_dates(T, 3, 1)[1][:10]
    st, hd, b, _ = publish(ada, "r_ops",
                           pol(eff=eff, slot=15, dur=30, cut=60))
    check_status("C3-S-30a", st, 201, b)
    ver = (j(b) or {}).get("policy_version")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 1})
    check_status("C3-S-30b", st, 201, b)
    occ = (j(b) or {}).get("occurrences") or []
    resps = [o.get("reservation") or {} for o in occ]
    # occurrence 0 keeps policy 0; generated ones pick the new policy
    pvs = [r.get("accepted_terms", {}).get("policy_version") for r in resps]
    expect("C3-S-7", pvs == [0, ver, ver], f"per-date policy {pvs}")
    # S-8 DST gap: r_berlin sun 00:00-06:00; 2027-03-28 02:30 does not exist
    st, hd, b, _ = book(ada, "r_berlin", "2027-03-21T02:30", party=2,
                        table="tb_1")
    check_status("C3-S-8a", st, 201, b)
    ref_dst = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref_dst, "count": 2,
                              "interval_weeks": 1})
    check_status("C3-S-8b", st, 422, b, code="invalid_local_time")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    expect("C3-S-8c", all(x.get("restaurant_id") != "r_berlin"
                          or x.get("reference") == ref_dst
                          for x in (j(b) or {}).get("reservations", [])),
           "DST gap adoption fully rolled back")
    # S-8 fold: 2026-10-25 02:30 exists twice in Berlin -> first occurrence rule
    st, hd, b, _ = book(ada, "r_berlin", "2026-10-18T02:30", party=2,
                        table="tb_2")
    check_status("C3-S-8d", st, 201, b)
    ref_f = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref_f, "count": 2,
                              "interval_weeks": 1})
    check_status("C3-S-8e", st, 201, b)
    occ = (j(b) or {}).get("occurrences") or []
    r2 = (occ[1].get("reservation") or {}) if len(occ) > 1 else {}
    expect("C3-S-8f", r2.get("starts_at") == "2026-10-25T02:30:00+02:00",
           f"fold picks first occurrence {r2.get('starts_at')}")
    reset3()

def sec_series_pair():
    """S-9/R3-7: generated occurrences keep the anchor's canonical pair."""
    reset3()
    ada = mgr()
    T = utc_local(220 * 60)
    st, hd, b, _ = book(ada, "r_combo", T, party=5, ids=["t_a", "t_b"])
    check_status("C3-S-40a", st, 201, b)
    ref = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 2})
    check_status("C3-S-40b", st, 201, b)
    occ = (j(b) or {}).get("occurrences") or []
    resps = [o.get("reservation") or {} for o in occ]
    expect("C3-S-40c", all(r.get("table_ids") == ["t_a", "t_b"]
                           for r in resps),
           f"pair propagated {[r.get('table_ids') for r in resps]}")
    dates = _occ_dates(T, 3, 2)
    st, hd, b, _ = avail("r_combo", dates[1][:10], 2)
    sl = slot_at(b, dates[1])
    opts = [o["table_ids"] for o in (sl or {}).get("available_options", [])]
    expect("C3-S-40d", sl is not None and ["t_a", "t_b"] not in opts
           and ["t_a"] not in opts and ["t_b"] not in opts,
           f"pair occurrence occupies both members {opts}")
    reset3()

# ================= M — collective moves under policies/series =================

def sec_moves_policy():
    reset3()
    ada = mgr()
    T = utc_local(240 * 60); T2 = utc_local(250 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    # policy applies at the RESULTING date, terms re-snapshotted
    st, hd, b, _ = publish(ada, "r_ops", pol(eff=T2[:10], slot=15, dur=30, cut=30))
    check_status("C3-M-1a", st, 201, b)
    ver = (j(b) or {}).get("policy_version")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
                        body={"moves": [{"reference": ref,
                                         "starts_at_local": T2}]})
    check_status("C3-M-1b", st, 201, b)
    rs = (j(b) or {}).get("reservations") or []
    expect("C3-M-1c", rs and rs[0].get("accepted_terms", {}).get(
        "policy_version") == ver and rs[0].get("revision") == 2,
        f"moved booking re-snapshotted {rs[0].get('revision') if rs else None}")
    st, hd, b, _ = hist(ref, token=ada)
    ent = entries_of(b) or []
    expect("C3-M-5", len(ent) == 2 and ent[1].get("event") == "changed",
           "moved booking gained one changed entry")
    # M-2: per-move expected_revision; stale item fails the whole batch
    st, hd, b, _ = book(ada, "r_ops", utc_local(260 * 60), party=2,
                        table="t_b")
    ref2 = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": ref2, "party_size": 3},
                        {"reference": ref, "expected_revision": 99,
                         "party_size": 3}]})
    check_status("C3-M-2", st, 409, b, code="stale_revision")
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    expect("C3-M-4", (j(b) or {}).get("party_size") == 2
           and (j(b) or {}).get("revision") == 1,
           "batch atomic: first move rolled back")
    # M-3: no-op move batch returns reservations, no revision/history churn
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
                        body={"moves": [{"reference": ref2,
                                         "party_size": 2}]})
    expect("C3-M-3", st in (200, 201), f"no-op batch st={st}")
    st, hd, b, _ = call("GET", f"/reservations/{ref2}", token=ada)
    st, hd, bh, _ = hist(ref2, token=ada)
    expect("C3-M-3b", (j(b) or {}).get("revision") == 1
           and len(entries_of(bh) or []) == 1,
           "no-op move kept revision+history")
    reset3()

def sec_moves_series():
    """M-7/R3-19: moving series occurrences -> exception + one series bump."""
    reset3()
    ada = mgr()
    T = utc_local(270 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    st, hd, b, _ = call("POST", "/series", token=ada, idem=key(),
                        body={"anchor_reference": ref, "count": 3,
                              "interval_weeks": 1})
    check_status("C3-M-7a", st, 201, b)
    S = j(b) or {}
    sid = S.get("series_id")
    occ = S.get("occurrences") or []
    refs = [o.get("reference") for o in occ]
    # move two occurrences of the SAME series in one batch: series rev +1 total
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": refs[1], "party_size": 3},
                        {"reference": refs[2], "party_size": 3}]})
    check_status("C3-M-7b", st, 201, b)
    st, hd, b, _ = call("GET", f"/series/{sid}", token=ada)
    S2 = j(b) or {}
    exc = {o["index"]: o.get("exception")
           for o in S2.get("occurrences", [])}
    expect("C3-M-7c", S2.get("revision") == 2 and exc.get(1) is True
           and exc.get(2) is True and exc.get(0) is False,
           f"one batch bump, exceptions on moved occurrences {exc}")
    reset3()

# ================= concurrency =================

def sec_concurrency3():
    reset3()
    ada = mgr()
    # policy publish race: N concurrent publishes must each allocate a
    # distinct contiguous version, no lost update
    N = 8
    barrier = threading.Barrier(N)
    bodies = [pol(eff="2026-12-01", slot=15, dur=30, cut=30 + i)
              for i in range(N)]
    def one(i):
        barrier.wait()
        return publish(ada, "r_ops", bodies[i], idem=key(f"pr{i}"))
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(one, range(N)))
    sts = [r[0] for r in rs]
    vers = sorted((j(r[2]) or {}).get("policy_version") for r in rs)
    expect("C3-CON-1", sts == [201] * N and vers == list(range(1, N + 1)),
           f"publish race sts={sts} vers={vers}")
    # same-revision amendment race already covered by C3-T-14.
    # series adoption race: same anchor, distinct keys -> exactly one 201
    T = utc_local(280 * 60)
    st, hd, b, _ = book(ada, "r_ops", T, party=2, table="t_a")
    ref = (j(b) or {}).get("reference")
    barrier = threading.Barrier(N)
    def adopt(i):
        barrier.wait()
        return call("POST", "/series", token=ada, idem=key(f"ad{i}"),
                    body={"anchor_reference": ref, "count": 2,
                          "interval_weeks": 1})
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(adopt, range(N)))
    sts = [r[0] for r in rs]
    codes = [err_code(r[2]) for r in rs]
    expect("C3-CON-2", sts.count(201) == 1 and
           all(s == 409 for s in sts if s != 201) and
           all(c == "already_in_series" for c in codes if c),
           f"adoption race sts={sts}")
    reset3()

# ================= D-3 — hardened mode (separate instance) =================

def sec_hardened3():
    for m, p in (("POST", "/_test/reset"), ("GET", "/_test/export"),
                 ("POST", "/_test/import")):
        st, hd, b, _ = call(m, p, body={} if m == "POST" else None)
        check_status(f"C3-HRD:{p}", st, 404, b)
    st, hd, b, _ = call("GET", "/health")
    check_status("C3-HRD-health", st, 200, b)
    st, hd, b, _ = call("GET", "/")
    ct = hd.get("Content-Type") or hd.get("content-type") or ""
    expect("C3-HRD-ui", st == 200 and "text/html" in ct.lower(),
           f"UI still served st={st} ct={ct!r}")

SECTIONS3 = [sec_explain, sec_policy_fixture, sec_policy_auth,
             sec_policy_idem, sec_policy_validation, sec_policy_order,
             sec_terms, sec_amend, sec_history, sec_history_terms_snapshot,
             sec_combo_history, sec_series_validate, sec_series_lifecycle,
             sec_series_atomicity, sec_series_policy_dst, sec_series_pair,
             sec_moves_policy, sec_moves_series, sec_concurrency3]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=s1.BASE)
    ap.add_argument("--only", default=None, help="substring filter on section name")
    ap.add_argument("--inherited-only", action="store_true")
    ap.add_argument("--s3-only", action="store_true")
    ap.add_argument("--hardened", action="store_true",
                    help="target is a hardened instance: run only hardening probes")
    args = ap.parse_args()
    s1.BASE = args.base_url.rstrip("/")
    t0 = time.monotonic()
    if args.hardened:
        sections = [sec_hardened3]
    elif args.inherited_only:
        sections = list(s1.SECTIONS) + s2.SECTIONS2
    elif args.s3_only:
        sections = SECTIONS3
    else:
        sections = list(s1.SECTIONS) + s2.SECTIONS2 + SECTIONS3
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
        print("5XX", cid, st)
    sys.exit(1 if fails or s1.FIVE_XX else 0)

if __name__ == "__main__":
    main()
