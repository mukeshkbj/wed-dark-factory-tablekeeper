#!/usr/bin/env python3
"""tk-verifier stage-2 black-box checks (spec-derived; stdlib only).

Inherits the COMPLETE stage-1 suite verbatim (imported module, unmodified)
and adds stage-2 sections. Every request has a hard timeout; a hang fails.

Usage:
  python checks.py --base-url http://localhost:8080     full suite
  python checks.py --base-url ... --inherited-only      stage-1 regression
  python checks.py --base-url ... --s2-only             stage-2 sections only
  python checks.py --base-url ... --hardened            hardened-instance probes
  python checks.py --base-url ... --only substring      section-name filter
"""
import argparse, importlib.util, json, pathlib, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

_HERE = pathlib.Path(__file__).resolve().parent

def _load_s1():
    p = _HERE.parent / "stage-1" / "checks.py"
    spec = importlib.util.spec_from_file_location("tk_s1_checks", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

s1 = _load_s1()
call = s1.call; j = s1.j; expect = s1.expect; note = s1.note
check_status = s1.check_status; err_code = s1.err_code; err_shape = s1.err_shape
key = s1.key; utc_local = s1.utc_local; login = s1.login; signup = s1.signup
WEEKDAYS = s1.WEEKDAYS; RFC3339 = s1.RFC3339

# ---------------- stage-2 fixtures ----------------
#
# r_combo (UTC, all-week 00:00-23:59, slot 15, dur 60, cutoff 120):
#   t_a cap 2, t_b cap 4, t_c cap 4; combinable [t_a,t_b] (=6), [t_b,t_c] (=8).
#   {t_a,t_c} is NOT declared -> exercises non-transitivity.
# r_anker gains a declared pair [t_1,t_2] so a spec-shaped restaurant shows it.

def fixture_combo():
    fx = s1.fixture_base()
    fx["restaurants"][0]["combinable"] = [["t_1", "t_2"]]
    fx["restaurants"].append({
        "id": "r_combo", "name": "Combo House", "timezone": "UTC",
        "slot_minutes": 15, "reservation_duration_minutes": 60,
        "cancellation_cutoff_minutes": 120,
        "opening_hours": [{"weekday": w, "opens": "00:00", "closes": "23:59"}
                          for w in WEEKDAYS],
        "combinable": [["t_a", "t_b"], ["t_b", "t_c"]],
        "tables": [{"id": "t_a", "label": "A", "capacity": 2},
                   {"id": "t_b", "label": "B", "capacity": 4},
                   {"id": "t_c", "label": "C", "capacity": 4}],
    })
    return fx

def reset2(fx=None, cid="C2-RT-0"):
    st, hd, b, dt = call("POST", "/_test/reset",
                         body=fx if fx is not None else fixture_combo(), timeout=15)
    if st != 204:
        expect(cid, False, f"reset st={st} body={b[:200]!r}")
        return False
    return True

def slot_at(avail_body, local):
    for s in (j(avail_body) or {}).get("slots", []):
        if s.get("starts_at_local") == local:
            return s
    return None

def avail(rid, date, ps):
    return call("GET", f"/availability?restaurant_id={rid}&date={date}&party_size={ps}")

# ---------------- C2-FX combinable fixture validation ----------------

def sec_fx_combinable():
    reset2()
    # combinable echoed in restaurant detail (fixture shape preserved)
    st, hd, b, _ = call("GET", "/restaurants/r_combo")
    check_status("C2-FX-1", st, 200, b)
    expect("C2-FX-1b", (j(b) or {}).get("combinable") == [["t_a", "t_b"], ["t_b", "t_c"]],
           f"combinable echoed {(j(b) or {}).get('combinable')}")
    st, hd, b, _ = call("GET", "/restaurants/r_anker")
    expect("C2-FX-1c", (j(b) or {}).get("combinable") == [["t_1", "t_2"]],
           f"anker combinable {(j(b) or {}).get('combinable')}")

    # invalid combinable payloads -> 422 validation_failed + state unchanged
    variants = {
        "three":       [["t_a", "t_b", "t_c"]],
        "one":         [["t_a"]],
        "empty_pair":  [[]],
        "dup_member":  [["t_a", "t_a"]],
        "unknown":     [["t_a", "t_zz"]],
        "foreign":     [["t_a", "t_1"]],          # t_1 belongs to r_anker
        "not_list":    "t_a",
        "entry_str":   ["t_a"],
        "elem_nonstr": [["t_a", 7]],
        "mixed":       [["t_a", "t_b"], "bogus"],
    }
    for tag, comb in variants.items():
        fx = fixture_combo(); fx["restaurants"][-1]["combinable"] = comb
        st, hd, b, _ = call("POST", "/_test/reset", body=fx, timeout=15)
        check_status(f"C2-FX-2:{tag}", st, 422, b, code="validation_failed")
        st, hd, b2, _ = call("GET", "/restaurants/r_combo")
        expect(f"C2-FX-2b:{tag}", st == 200 and
               (j(b2) or {}).get("combinable") == [["t_a", "t_b"], ["t_b", "t_c"]],
               "state unchanged after invalid combinable reset")

    # duplicate equivalent pairs collapse; canonical order = first occurrence
    fx = fixture_combo()
    fx["restaurants"][-1]["combinable"] = [["t_b", "t_a"], ["t_a", "t_b"],
                                          ["t_b", "t_c"], ["t_c", "t_b"]]
    reset2(fx)
    D = utc_local(26 * 60)[:10]
    st, hd, b, _ = avail("r_combo", D, 2)
    sl = (j(b) or {}).get("slots") or []
    opts = sl[0].get("available_options") if sl else None
    pairs = [o["table_ids"] for o in (opts or []) if len(o.get("table_ids", [])) == 2]
    expect("C2-FX-3", pairs == [["t_b", "t_a"], ["t_b", "t_c"]],
           f"dup-collapse canonical order {pairs}")

    # seeded reservation with table_ids (declared pair) occupies both members
    T2 = utc_local(30 * 60); D2 = T2[:10]
    fx = fixture_combo()
    fx["reservations"] = [{"id": "rs_pair", "reference": "SEED01", "user_id": "u_ada",
                           "restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
                           "starts_at_local": T2, "party_size": 4}]
    reset2(fx)
    st, hd, b, _ = avail("r_combo", D2, 2)
    sl = slot_at(b, T2)
    opts = [o["table_ids"] for o in (sl or {}).get("available_options", [])]
    expect("C2-FX-4", sl is not None and opts == [["t_c"]],
           f"seeded pair blocks members+pairs: {opts}")
    ada = login("ada@example.com", "correct horse")[1]["token"]
    st, hd, b, _ = call("GET", "/reservations/SEED01", token=ada)
    expect("C2-FX-4b", st == 200 and (j(b) or {}).get("table_ids") == ["t_a", "t_b"]
           and (j(b) or {}).get("status") == "confirmed",
           f"seeded pair view {b[:120]!r}")
    # seeded singleton table_ids works; seeded cancelled pair occupies nothing
    fx = fixture_combo()
    fx["reservations"] = [
        {"id": "rs_s", "reference": "SEED02", "user_id": "u_ada",
         "restaurant_id": "r_combo", "table_ids": ["t_c"],
         "starts_at_local": T2, "party_size": 2},
        {"id": "rs_x", "reference": "SEED03", "user_id": "u_ada",
         "restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
         "starts_at_local": T2, "party_size": 4, "status": "cancelled"}]
    reset2(fx)
    st, hd, b, _ = avail("r_combo", D2, 2)
    sl = slot_at(b, T2)
    opts = [o["table_ids"] for o in (sl or {}).get("available_options", [])]
    expect("C2-FX-5", opts == [["t_a"], ["t_b"], ["t_a", "t_b"]],
           f"cancelled seed does not occupy; single seed holds t_c: {opts}")
    # incoherent seeds -> 422 + state unchanged
    for tag, mut in {
        "undeclared": dict(table_ids=["t_a", "t_c"]),
        "both_fields": dict(table_id="t_a", table_ids=["t_a", "t_b"]),
    }.items():
        fx = fixture_combo()
        ent = {"id": "rs_bad", "reference": "SEED09", "user_id": "u_ada",
               "restaurant_id": "r_combo", "starts_at_local": T2, "party_size": 4}
        ent.update(mut)
        fx["reservations"] = [ent]
        st, hd, b, _ = call("POST", "/_test/reset", body=fx, timeout=15)
        check_status(f"C2-FX-6:{tag}", st, 422, b, code="validation_failed")
        st, hd, b2, _ = call("GET", "/restaurants/r_combo")
        expect(f"C2-FX-6b:{tag}", st == 200, "state unchanged after bad seed")
    # over-capacity seed: NOT rejected at reset (stage-1 fixture floor has no
    # capacity-fit rule for seeds — coherence floor covers pair membership,
    # grid and hours only). The seed must still occupy its members.
    fx = fixture_combo()
    fx["reservations"] = [{"id": "rs_big", "reference": "SEED10", "user_id": "u_ada",
                           "restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
                           "starts_at_local": T2, "party_size": 9}]
    st, hd, b, _ = call("POST", "/_test/reset", body=fx, timeout=15)
    check_status("C2-FX-7", st, 204, b)
    sl = slot_at(avail("r_combo", T2[:10], 2)[2], T2)
    opts = [o["table_ids"] for o in (sl or {}).get("available_options", [])]
    expect("C2-FX-7b", opts == [["t_c"]], f"over-cap seed occupies members {opts}")
    note("C2-FX-7c", "seed party_size>capacity accepted; capacity-fit on seeds "
         "is not a stated rejection rule (stage-1 floor parity)")
    reset2()

# ---------------- C2-RT screen routes ----------------

def sec_routes():
    reset2()
    for p in ("/", "/signup", "/login", "/lookup"):
        st, hd, b, _ = call("GET", p)
        ct = hd.get("Content-Type") or hd.get("content-type") or ""
        expect(f"C2-RT:{p}", st == 200 and "text/html" in ct.lower(),
               f"st={st} ct={ct!r}")

# ---------------- C2-AVO available_options ----------------

OPT = lambda ids, cap: {"table_ids": list(ids), "capacity": cap}
OPTS_EMPTY = [OPT(["t_a"], 2), OPT(["t_b"], 4), OPT(["t_c"], 4),
              OPT(["t_a", "t_b"], 6), OPT(["t_b", "t_c"], 8)]

def sec_available_options():
    reset2()
    ada = login("ada@example.com", "correct horse")[1]["token"]
    T = utc_local(24 * 60); D = T[:10]
    want_by_ps = {
        2: OPTS_EMPTY,
        4: OPTS_EMPTY[1:],
        5: OPTS_EMPTY[3:],                    # no single fits; both pairs do
        7: [OPT(["t_b", "t_c"], 8)],          # only the bigger pair
        9: [],                                # nothing fits
    }
    for ps, want in want_by_ps.items():
        st, hd, b, _ = avail("r_combo", D, ps)
        check_status(f"C2-AVO-1:p{ps}", st, 200, b)
        sl = slot_at(b, T)
        got = (sl or {}).get("available_options")
        expect(f"C2-AVO-2:p{ps}", got == want, f"options {got} != {want}")
        # every slot carries the key (empty allowed)
        slots = (j(b) or {}).get("slots", [])
        expect(f"C2-AVO-3:p{ps}", slots and all("available_options" in x for x in slots),
               "available_options present on every slot")
        # available_table_ids stays singles-only
        ati = (sl or {}).get("available_table_ids")
        singles_want = [t for t, c in (("t_a", 2), ("t_b", 4), ("t_c", 4)) if c >= ps]
        expect(f"C2-AVO-4:p{ps}", ati == singles_want, f"table_ids {ati}")
        # option object shape: exactly {table_ids, capacity}
        expect(f"C2-AVO-5:p{ps}", all(set(o.keys()) == {"table_ids", "capacity"}
               for o in (got or [])), "option field shape")
    # member occupancy removes the single AND every pair containing it
    book = {"restaurant_id": "r_combo", "table_id": "t_a",
            "starts_at_local": T, "party_size": 2}
    st, hd, b, _ = call("POST", "/reservations", body=book, token=ada, idem=key())
    check_status("C2-AVO-6:setup", st, 201, b)
    st, hd, b, _ = avail("r_combo", D, 2)
    sl = slot_at(b, T)
    expect("C2-AVO-7", (sl or {}).get("available_options") ==
           [OPT(["t_b"], 4), OPT(["t_c"], 4), OPT(["t_b", "t_c"], 8)],
           f"member occupied: {(sl or {}).get('available_options')}")
    expect("C2-AVO-7b", (sl or {}).get("available_table_ids") == ["t_b", "t_c"],
           "singles list excludes taken member")
    # a booked pair removes both members and every pair touching either
    T2 = utc_local(30 * 60)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
                        body={"restaurant_id": "r_combo", "table_ids": ["t_b", "t_c"],
                              "starts_at_local": T2, "party_size": 6})
    check_status("C2-AVO-8:setup", st, 201, b)
    sl = slot_at(avail("r_combo", T2[:10], 2)[2], T2)
    expect("C2-AVO-9", (sl or {}).get("available_options") == [OPT(["t_a"], 2)],
           f"pair blocks both members: {(sl or {}).get('available_options')}")
    # cancelling the pair frees both members and restores pair options
    ref = (j(b) or {}).get("reference")
    call("POST", f"/reservations/{ref}/cancel", token=ada)
    sl = slot_at(avail("r_combo", T2[:10], 2)[2], T2)
    expect("C2-AVO-10", (sl or {}).get("available_options") == OPTS_EMPTY,
           "cancelled pair frees every member")
# ---------------- C2-BKC create with table_ids ----------------

def sec_combo_create():
    reset2()
    ada = login("ada@example.com", "correct horse")[1]["token"]
    T = utc_local(40 * 60)
    # declared pair, party 5 (no single fits, sum does)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
              "starts_at_local": T, "party_size": 5})
    check_status("C2-BKC-1", st, 201, b)
    r = j(b) or {}
    expect("C2-BKC-1b", r.get("table_ids") == ["t_a", "t_b"] and "table_id" not in r,
           f"pair response shape {sorted(r)}")
    ref_pair = r.get("reference")
    # reversed member order = same unordered pair, canonicalised
    T2 = utc_local(45 * 60)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_b", "t_a"],
              "starts_at_local": T2, "party_size": 2})
    check_status("C2-BKC-2", st, 201, b)
    expect("C2-BKC-2b", (j(b) or {}).get("table_ids") == ["t_a", "t_b"],
           f"canonical order {(j(b) or {}).get('table_ids')}")
    # one-element table_ids = legal single; response carries BOTH shapes
    T3 = utc_local(50 * 60)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_c"],
              "starts_at_local": T3, "party_size": 2})
    check_status("C2-BKC-3", st, 201, b)
    r = j(b) or {}
    expect("C2-BKC-3b", r.get("table_id") == "t_c" and r.get("table_ids") == ["t_c"],
           f"singleton response {sorted(r)}")
    # both fields -> 422 validation_failed
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_id": "t_a", "table_ids": ["t_b"],
              "starts_at_local": utc_local(55 * 60), "party_size": 2})
    check_status("C2-BKC-4", st, 422, b, code="validation_failed")
    # malformed sets
    for tag, ids in (("empty", []), ("dup", ["t_a", "t_a"])):
        st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
            body={"restaurant_id": "r_combo", "table_ids": ids,
                  "starts_at_local": utc_local(56 * 60), "party_size": 2})
        check_status(f"C2-BKC-5:{tag}", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b", "t_c"],
              "starts_at_local": utc_local(57 * 60), "party_size": 2})
    check_status("C2-BKC-6", st, 422, b, code="combination_not_allowed")
    # undeclared pair AND non-transitivity ({t_a,t_c} never declared)
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_c"],
              "starts_at_local": utc_local(58 * 60), "party_size": 2})
    check_status("C2-BKC-7", st, 422, b, code="combination_not_allowed")
    # pair on r_anker: declared [t_1,t_2]; reversed request canonicalised
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_anker", "table_ids": ["t_2", "t_1"],
              "starts_at_local": "2026-09-24T19:00", "party_size": 4})
    check_status("C2-BKC-7b", st, 201, b)
    expect("C2-BKC-7c", (j(b) or {}).get("table_ids") == ["t_1", "t_2"],
           "anker pair canonicalised")
    # member-occupancy conflicts (pair already holds T on t_a+t_b)
    for tag, ids, when in (("member", ["t_a"], T),
                           ("member_overlap", ["t_b"], utc_local(40 * 60 + 15)),
                           ("pair_sharing", ["t_b", "t_c"], T)):
        st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
            body={"restaurant_id": "r_combo", "table_ids": ids,
                  "starts_at_local": when, "party_size": 2})
        check_status(f"C2-BKC-8:{tag}", st, 409, b, code="table_unavailable")
    # summed capacity bound
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
              "starts_at_local": utc_local(59 * 60), "party_size": 7})
    check_status("C2-BKC-9", st, 422, b, code="party_exceeds_capacity")
    # existence rules per member
    for tag, ids in (("unknown", ["t_a", "t_zz"]), ("foreign", ["t_a", "t_1"])):
        st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
            body={"restaurant_id": "r_combo", "table_ids": ids,
                  "starts_at_local": utc_local(60 * 60), "party_size": 2})
        check_status(f"C2-BKC-10:{tag}", st, 404, b, code="not_found")
    # wrong JSON types for the field itself
    for tag, ids in (("str", "t_a"), ("int", 7)):
        st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
            body={"restaurant_id": "r_combo", "table_ids": ids,
                  "starts_at_local": utc_local(61 * 60), "party_size": 2})
        check_status(f"C2-BKC-11:{tag}", st, 400, b, code="malformed_request")
    # type-blur observations (spec silent; must never 5xx)
    for tag, ids in (("null", None), ("elem_int", ["t_a", 7])):
        st, hd, b, _ = call("POST", "/reservations", token=ada, idem=key(),
            body={"restaurant_id": "r_combo", "table_ids": ids,
                  "starts_at_local": utc_local(62 * 60), "party_size": 2})
        check_status(f"C2-BKC-12:{tag}", st, (400, 422), b)
    # views emit table_ids always; table_id iff singleton
    st, hd, b, _ = call("GET", f"/reservations/{ref_pair}", token=ada)
    r = j(b) or {}
    expect("C2-BKC-13", st == 200 and r.get("table_ids") == ["t_a", "t_b"]
           and "table_id" not in r, f"pair GET shape {sorted(r)}")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    lst = (j(b) or {}).get("reservations", [])
    ok = all("table_ids" in x for x in lst) and \
         all(("table_id" in x) == (len(x.get("table_ids", [])) == 1) for x in lst)
    expect("C2-BKC-13b", ok, "list view shape rule")

# ---------------- C2-PATC patch / moves with sets ----------------

def sec_combo_patch_moves():
    reset2()
    ada = login("ada@example.com", "correct horse")[1]["token"]
    T = utc_local(70 * 60); T2 = utc_local(76 * 60); T3 = utc_local(82 * 60)
    def mk(ids, when, party=2, fld="table_ids"):
        body = {"restaurant_id": "r_combo", fld: ids,
                "starts_at_local": when, "party_size": party}
        st, hd, b, _ = call("POST", "/reservations", body=body, token=ada, idem=key())
        return st, j(b) or {}
    st, r1 = mk(["t_c"], T); rf1 = r1.get("reference")
    # PATCH single -> pair
    st, hd, b, _ = call("PATCH", f"/reservations/{rf1}", token=ada,
                        body={"table_ids": ["t_a", "t_b"]})
    check_status("C2-PATC-1", st, 200, b)
    expect("C2-PATC-1b", (j(b) or {}).get("table_ids") == ["t_a", "t_b"]
           and "table_id" not in (j(b) or {}), "single->pair shape")
    # PATCH pair -> singleton list restores table_id
    st, hd, b, _ = call("PATCH", f"/reservations/{rf1}", token=ada,
                        body={"table_ids": ["t_c"]})
    check_status("C2-PATC-2", st, 200, b)
    expect("C2-PATC-2b", (j(b) or {}).get("table_id") == "t_c"
           and (j(b) or {}).get("table_ids") == ["t_c"], "pair->single shape")
    # both fields -> 422; undeclared pair -> 422 combination_not_allowed
    st, hd, b, _ = call("PATCH", f"/reservations/{rf1}", token=ada,
                        body={"table_id": "t_a", "table_ids": ["t_a", "t_b"]})
    check_status("C2-PATC-3", st, 422, b, code="validation_failed")
    st, hd, b, _ = call("PATCH", f"/reservations/{rf1}", token=ada,
                        body={"table_ids": ["t_a", "t_c"]})
    check_status("C2-PATC-4", st, 422, b, code="combination_not_allowed")
    # failed PATCH leaves original (set unchanged)
    st, hd, b, _ = call("GET", f"/reservations/{rf1}", token=ada)
    expect("C2-PATC-4b", (j(b) or {}).get("table_ids") == ["t_c"],
           "failed patch kept original set")
    # collision: member of target set held by another booking
    st, r2 = mk(["t_b"], T2); rf2 = r2.get("reference")
    st, r3 = mk(["t_a"], T2); rf3 = r3.get("reference")
    st, hd, b, _ = call("PATCH", f"/reservations/{rf2}", token=ada,
                        body={"table_ids": ["t_a", "t_b"]})
    check_status("C2-PATC-5", st, 409, b, code="table_unavailable")
    st, hd, b, _ = call("GET", f"/reservations/{rf2}", token=ada)
    expect("C2-PATC-5b", (j(b) or {}).get("table_id") == "t_b", "atomicity kept t_b")
    # moves: single -> pair, then collision all-or-nothing
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": rf2, "table_ids": ["t_b", "t_c"]}]})
    check_status("C2-MVC-1", st, 201, b)
    expect("C2-MVC-1b", ((j(b) or {}).get("reservations") or [{}])[0].get("table_ids")
           == ["t_b", "t_c"], "move to pair")
    st, r4 = mk(["t_c"], T3); rf4 = r4.get("reference")
    st, r5 = mk(["t_a"], T3); rf5 = r5.get("reference")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": rf4, "table_ids": ["t_a", "t_c"]}]})
    check_status("C2-MVC-2", st, 422, b, code="combination_not_allowed")
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": rf4, "table_id": "t_b",
                         "table_ids": ["t_b", "t_c"]}]})
    check_status("C2-MVC-3", st, 422, b, code="validation_failed")
    # move rf4 -> pair [t_a,t_b] would collide with rf5 (t_a) at T3
    st, hd, b, _ = call("POST", "/reservation-moves", token=ada, idem=key(),
        body={"moves": [{"reference": rf4, "table_ids": ["t_a", "t_b"]},
                        {"reference": rf5, "party_size": 2}]})
    check_status("C2-MVC-4", st, 409, b, code="table_unavailable")
    st, hd, b, _ = call("GET", f"/reservations/{rf4}", token=ada)
    expect("C2-MVC-4b", (j(b) or {}).get("table_id") == "t_c", "atomic rollback")

# ---------------- C2-IDMC idempotency on combos ----------------

def sec_combo_idem():
    reset2()
    ada = login("ada@example.com", "correct horse")[1]["token"]
    T = utc_local(90 * 60)
    K = key("c2")
    body = {"restaurant_id": "r_combo", "table_ids": ["t_b", "t_c"],
            "starts_at_local": T, "party_size": 6}
    st, hd, b, _ = call("POST", "/reservations", body=body, token=ada, idem=K)
    check_status("C2-IDMC-1", st, 201, b)
    orig = j(b); ref = orig.get("reference")
    st, hd, b, _ = call("POST", "/reservations", body=body, token=ada, idem=K)
    check_status("C2-IDMC-2", st, 200, b)
    expect("C2-IDMC-2b", j(b) == orig, "pair replay identical")
    # replay returns ORIGINAL body even after amendment and cancellation
    call("PATCH", f"/reservations/{ref}", body={"party_size": 3}, token=ada)
    st, hd, b, _ = call("POST", "/reservations", body=body, token=ada, idem=K)
    check_status("C2-IDMC-3", st, 200, b)
    expect("C2-IDMC-3b", j(b) == orig, "replay stale-original after PATCH")
    call("POST", f"/reservations/{ref}/cancel", token=ada)
    st, hd, b, _ = call("POST", "/reservations", body=body, token=ada, idem=K)
    check_status("C2-IDMC-4", st, 200, b)
    expect("C2-IDMC-4b", j(b) == orig, "replay stale-original after cancel")
    # same key different body -> 409
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=K,
        body=dict(body, party_size=4))
    check_status("C2-IDMC-5", st, 409, b, code="idempotency_key_reuse")
    # failed combo frees the key
    KF = key("c2f")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=KF,
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_c"],
              "starts_at_local": utc_local(96 * 60), "party_size": 2})
    check_status("C2-IDMC-6", st, 422, b, code="combination_not_allowed")
    st, hd, b, _ = call("POST", "/reservations", token=ada, idem=KF,
        body={"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
              "starts_at_local": utc_local(96 * 60), "party_size": 2})
    check_status("C2-IDMC-6b", st, 201, b)
    # 50-way identical pair create: one 201, rest 200 same body, one booking
    N = 50
    K2 = key("c2race")
    body2 = {"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
             "starts_at_local": utc_local(102 * 60), "party_size": 4}
    barrier = threading.Barrier(N)
    def one():
        barrier.wait()
        return call("POST", "/reservations", body=body2, token=ada, idem=K2)
    with ThreadPoolExecutor(N) as ex:
        rs = list(ex.map(lambda _: one(), range(N)))
    sts = [r[0] for r in rs]
    bodies = [j(r[2]) for r in rs]
    expect("C2-IDMC-7", sts.count(201) == 1 and sts.count(200) == N - 1,
           f"sts histogram 201x{sts.count(201)} 200x{sts.count(200)} other={N-sts.count(201)-sts.count(200)}")
    winners = [bd for s, bd in zip(sts, bodies) if s == 201]
    expect("C2-IDMC-7b", winners and all(bd == winners[0] for bd in bodies),
           "all replay bodies identical")
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    n = sum(1 for x in (j(b) or {}).get("reservations", [])
            if x.get("starts_at_local") == body2["starts_at_local"]
            and x.get("table_ids") == ["t_a", "t_b"])
    expect("C2-IDMC-7c", n == 1, f"exactly one pair booking, got {n}")

# ---------------- C2-CONC concurrency on combos ----------------

def sec_combo_concurrency():
    reset2()
    ada = login("ada@example.com", "correct horse")[1]["token"]
    def race(bodies, tag):
        N = len(bodies); barrier = threading.Barrier(N)
        def one(i):
            barrier.wait()
            return call("POST", "/reservations", body=bodies[i],
                        token=ada, idem=key(f"{tag}{i}"))
        with ThreadPoolExecutor(N) as ex:
            return list(ex.map(one, range(N)))
    # pair vs member race: share t_a -> at most one booking wins
    T = utc_local(110 * 60)
    bs = ([{"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
            "starts_at_local": T, "party_size": 4}] * 12 +
          [{"restaurant_id": "r_combo", "table_id": "t_a",
            "starts_at_local": T, "party_size": 2}] * 12)
    rs = race(bs, "pm")
    sts = [r[0] for r in rs]
    expect("C2-CONC-1", sts.count(201) == 1 and sts.count(409) == len(bs) - 1,
           f"pair-vs-member sts={ {s: sts.count(s) for s in set(sts)} }")
    # overlapping pairs share t_b -> at most one wins
    T2 = utc_local(116 * 60)
    bs = ([{"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
            "starts_at_local": T2, "party_size": 4}] * 12 +
          [{"restaurant_id": "r_combo", "table_ids": ["t_b", "t_c"],
            "starts_at_local": T2, "party_size": 6}] * 12)
    sts = [r[0] for r in race(bs, "pp")]
    expect("C2-CONC-2", sts.count(201) == 1 and sts.count(409) == len(bs) - 1,
           f"pair-vs-pair sts={ {s: sts.count(s) for s in set(sts)} }")
    # disjoint options must NOT false-conflict: competing requests for
    # single t_c and for pair [t_a,t_b] share no table, so the race must
    # produce exactly one winner per group: 1 pair 201 + 1 single 201.
    T3 = utc_local(122 * 60)
    bs = ([{"restaurant_id": "r_combo", "table_ids": ["t_a", "t_b"],
            "starts_at_local": T3, "party_size": 4}] * 8 +
          [{"restaurant_id": "r_combo", "table_id": "t_c",
            "starts_at_local": T3, "party_size": 2}] * 8)
    sts = [r[0] for r in race(bs, "dj")]
    expect("C2-CONC-3", sts.count(201) == 2 and sts.count(409) == len(bs) - 2,
           f"disjoint race sts={ {s: sts.count(s) for s in set(sts)} }")
    # conservation: no table held twice at overlapping intervals
    st, hd, b, _ = call("GET", "/reservations", token=ada)
    held = {}
    for x in (j(b) or {}).get("reservations", []):
        if x.get("status") != "confirmed" or x.get("restaurant_id") != "r_combo":
            continue
        for t in x.get("table_ids") or [x.get("table_id")]:
            held.setdefault(t, []).append(x["starts_at_local"])
    ok = True
    for t, starts in held.items():
        ss = sorted(starts)
        for a, b_ in zip(ss, ss[1:]):
            if a[:16] == b_[:16] or (a < b_ and a[:10] == b_[:10] and
               (int(b_[11:13]) * 60 + int(b_[14:16])) -
               (int(a[11:13]) * 60 + int(a[14:16])) < 60):
                ok = False
    expect("C2-CONC-4", ok, f"per-table occupancy conserved {held}")

# ---------------- hardened mode (separate instance) ----------------

def sec_hardened():
    for m, p in (("POST", "/_test/reset"), ("GET", "/_test/export"),
                 ("POST", "/_test/import")):
        st, hd, b, _ = call(m, p, body={} if m == "POST" else None)
        check_status(f"C2-HRD:{p}", st, 404, b)
    st, hd, b, _ = call("GET", "/health")
    check_status("C2-HRD-health", st, 200, b)
    st, hd, b, _ = call("GET", "/")
    ct = hd.get("Content-Type") or hd.get("content-type") or ""
    expect("C2-HRD-ui", st == 200 and "text/html" in ct.lower(),
           f"UI still served st={st} ct={ct!r}")

SECTIONS2 = [sec_fx_combinable, sec_routes, sec_available_options,
             sec_combo_create, sec_combo_patch_moves, sec_combo_idem,
             sec_combo_concurrency]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=s1.BASE)
    ap.add_argument("--only", default=None, help="substring filter on section name")
    ap.add_argument("--inherited-only", action="store_true")
    ap.add_argument("--s2-only", action="store_true")
    ap.add_argument("--hardened", action="store_true",
                    help="target is a hardened instance: run only hardening probes")
    args = ap.parse_args()
    s1.BASE = args.base_url.rstrip("/")
    t0 = time.monotonic()
    if args.hardened:
        sections = [sec_hardened]
    elif args.inherited_only:
        sections = list(s1.SECTIONS)
    elif args.s2_only:
        sections = SECTIONS2
    else:
        sections = list(s1.SECTIONS) + SECTIONS2
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
