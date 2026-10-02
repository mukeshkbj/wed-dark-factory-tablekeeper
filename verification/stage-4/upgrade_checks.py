#!/usr/bin/env python3
"""tk-verifier stage-4: upgrade/import continuity (X).

R4-23: exports/imports preserve `plans` and `closures`; exports from
earlier stages lacking those fields import them as empty.

  X-1  stage-1, stage-2 and stage-3 exports all import into stage-4 -> 204
  X-2  imported reservations normalise (rev1, policy-0 terms), history +
       decision endpoints serve them, pending retries recover
  X-3  pre-upgrade tokens/references stay valid; imported bookings are
       adoptable into series (stage-3+ shape)
  X-4  an s3 export lacking plans/closures imports them EMPTY: no phantom
       closures block availability afterwards
  X-5  failed import leaves destination state untouched
  X-6  stage-4 round-trip preserves plans (pending + applied), closures,
       series, policies, histories and revisions

Usage:
  python upgrade_checks.py --s1-url ... --s2-url ... --s3-url ... --s4-url ...
"""
import argparse, json, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

S1 = "http://localhost:8091"; S2 = "http://localhost:8092"
S3 = "http://localhost:8093"; S4 = "http://localhost:8094"
RESULTS = []
TMO = 15

def call(base, method, path, body=None, raw=None, token=None, idem=None):
    data, h = None, {}
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode()
        h["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    if token: h["Authorization"] = "Bearer " + token
    if idem: h["Idempotency-Key"] = idem
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=TMO) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def j(b):
    try: return json.loads(b)
    except Exception: return None

def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok)))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)

def err_code(body):
    e = (j(body) or {}).get("error")
    return e.get("code") if isinstance(e, dict) else e

def utc_local(minutes_from_now):
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    dt = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
    if dt.hour >= 23: dt = dt.replace(hour=22, minute=45)
    return dt.strftime("%Y-%m-%dT%H:%M")

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def dt_utc(minutes_from_now):
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    dt = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
    if dt.hour >= 23: dt = dt.replace(hour=22, minute=45)
    return dt

WEEK = ["mon","tue","wed","thu","fri","sat","sun"]

def fixture_1():
    return {
        "users": [{"id": "u_ada", "email": "ada@example.com",
                   "password": "correct horse", "display_name": "Ada"},
                  {"id": "u_bob", "email": "bob@example.com",
                   "password": "second horse", "display_name": "Bob"}],
        "restaurants": [{"id": "r_ops", "name": "Ops Haus", "timezone": "UTC",
            "slot_minutes": 15, "reservation_duration_minutes": 60,
            "cancellation_cutoff_minutes": 120,
            "opening_hours": [{"weekday": w, "opens": "00:00",
                               "closes": "23:59"} for w in WEEK],
            "tables": [{"id": "t_a", "label": "A", "capacity": 4},
                       {"id": "t_b", "label": "B", "capacity": 4}]}],
        "reservations": []}

def fixture_2():
    fx = fixture_1()
    fx["restaurants"][0]["combinable"] = [["t_a", "t_b"]]
    return fx

def fixture_3():
    """Stage-3-shaped: managers + combinable (policies need a manager)."""
    fx = fixture_2()
    fx["restaurants"][0]["manager_user_ids"] = ["u_ada"]
    return fx

def _login(base):
    st, hd, b = call(base, "POST", "/auth/login",
                     body={"email": "ada@example.com",
                           "password": "correct horse"})
    return st, (j(b) or {}).get("token")

def _prep_source(base, fx, tag, manager=False):
    st, hd, b = call(base, "POST", "/_test/reset", body=fx)
    expect(f"X-{tag}-0", st == 204, f"source reset st={st}")
    st, ada = _login(base)
    expect(f"X-{tag}-0b", st == 200 and ada, "source login")
    T1 = utc_local(300)
    st, hd, b = call(base, "POST", "/reservations", token=ada,
                     idem=f"upg-{tag}-k1",
                     body={"restaurant_id": "r_ops", "table_id": "t_a",
                           "starts_at_local": T1, "party_size": 2})
    keep = j(b) or {}
    expect(f"X-{tag}-0c", st == 201 and keep.get("reference"),
           f"source booking st={st}")
    lost_body = {"restaurant_id": "r_ops", "table_id": "t_b",
                 "starts_at_local": utc_local(400), "party_size": 3}
    st, hd, b = call(base, "POST", "/reservations", token=ada,
                     idem=f"upg-{tag}-lost", body=lost_body)
    lost = j(b)
    expect(f"X-{tag}-0d", st == 201 and (lost or {}).get("reference"),
           "lost-response booking committed")
    # stage-3 sources also carry a policy + series state
    if manager:
        pol = {"effective_from": "2026-10-01", "slot_minutes": 15,
               "reservation_duration_minutes": 30,
               "cancellation_cutoff_minutes": 60,
               "opening_hours": [{"weekday": w, "opens": "00:00",
                                  "closes": "23:59"} for w in WEEK],
               "capacities": {"t_a": 4, "t_b": 4}}
        st, hd, b = call(base, "POST", "/restaurants/r_ops/policies",
                         token=ada, idem=f"upg-{tag}-pol", body=pol)
        expect(f"X-{tag}-0f", st == 201, f"source policy st={st}")
        st, hd, b = call(base, "POST", "/series", token=ada,
                         idem=f"upg-{tag}-ser",
                         body={"anchor_reference": keep["reference"],
                               "count": 2, "interval_weeks": 1})
        expect(f"X-{tag}-0g", st == 201, f"source series st={st}")
    st, hd, b = call(base, "GET", "/_test/export")
    exp = j(b)
    expect(f"X-{tag}-0e", st == 200 and isinstance(exp, dict)
           and exp.get("track") == "tablekeeper", "source export shape")
    return ada, keep, lost, lost_body, exp

def _check_imported(tag, ada, keep, lost, lost_body, series_ok):
    st, hd, b = call(S4, "GET", "/reservations", token=ada)
    expect(f"X-{tag}-3a", st == 200, f"token survives st={st}")
    refs = {x.get("reference") for x in (j(b) or {}).get("reservations", [])}
    expect(f"X-{tag}-3b", keep.get("reference") in refs
           and lost.get("reference") in refs, f"refs visible {refs}")
    st, hd, b = call(S4, "GET", f"/reservations/{keep['reference']}",
                     token=ada)
    r = j(b) or {}
    terms = r.get("accepted_terms") or {}
    expect(f"X-{tag}-4a", st == 200 and r.get("revision") == 1
           and terms.get("policy_version") == 0,
           f"normalised rev/terms {r.get('revision')} "
           f"{terms.get('policy_version')}")
    st, hd, b = call(S4, "GET", f"/reservations/{keep['reference']}/history",
                     token=ada)
    ent = (j(b) or {}).get("entries") or []
    expect(f"X-{tag}-4b", st == 200 and len(ent) >= 1
           and ent[0].get("event") == "created",
           f"imported history reconstructed n={len(ent)}")
    st, hd, b = call(S4, "GET", f"/reservations/{keep['reference']}/decision",
                     token=ada)
    expect(f"X-{tag}-4c", st == 200
           and (j(b) or {}).get("revision") == 1, "decision on import")
    st, hd, b = call(S4, "POST", "/reservations", token=ada,
                     idem=f"upg-{tag}-lost", body=lost_body)
    expect(f"X-{tag}-3c", st == 200 and j(b) == lost,
           f"lost retry recovered st={st}")
    if series_ok:
        st, hd, b = call(S4, "POST", "/series", token=ada,
                         idem=f"upg-{tag}-ser2",
                         body={"anchor_reference": lost["reference"],
                               "count": 2, "interval_weeks": 1})
        expect(f"X-{tag}-2", st == 201,
               f"adopt imported into series st={st}")

def avail_opts(rid, date, ps, slot):
    st, hd, b = call(S4, "GET",
                     f"/availability?restaurant_id={rid}&date={date}"
                     f"&party_size={ps}")
    for s in (j(b) or {}).get("slots", []):
        if s.get("starts_at_local") == slot:
            return [o["table_ids"] for o in s.get("available_options", [])]
    return None

def main():
    global S1, S2, S3, S4
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1-url", default=S1)
    ap.add_argument("--s2-url", default=S2)
    ap.add_argument("--s3-url", default=S3)
    ap.add_argument("--s4-url", default=S4)
    args = ap.parse_args()
    S1 = args.s1_url.rstrip("/"); S2 = args.s2_url.rstrip("/")
    S3 = args.s3_url.rstrip("/"); S4 = args.s4_url.rstrip("/")
    t0 = time.monotonic()

    # ---- leg A: stage-1 source -> stage-4 ----
    ada, keep, lost, lost_body, exp = _prep_source(S1, fixture_1(), "s1")
    st, hd, b = call(S4, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s1-1", st == 204, f"s1 export -> s4 import st={st}")
    _check_imported("s1", ada, keep, lost, lost_body, series_ok=True)

    # ---- leg B: stage-2 source -> stage-4 ----
    ada, keep, lost, lost_body, exp = _prep_source(S2, fixture_2(), "s2")
    st, hd, b = call(S4, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s2-1", st == 204, f"s2 export -> s4 import st={st}")
    _check_imported("s2", ada, keep, lost, lost_body, series_ok=True)

    # ---- leg C: stage-3 source -> stage-4 (policies+series, NO
    # plans/closures fields -> must import as EMPTY, R4-23) ----
    ada, keep, lost, lost_body, exp = _prep_source(
        S3, fixture_3(), "s3", manager=True)
    st, hd, b = call(S4, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s3-1", st == 204, f"s3 export -> s4 import st={st}")
    _check_imported("s3", ada, keep, lost, lost_body, series_ok=False)
    # X-4: the s3 export carried series + policy state; assert they landed
    src_sers = ((exp or {}).get("state") or {}).get("series") or {}
    src_sid = next(iter(src_sers), None) if isinstance(src_sers, dict) else None
    st, hd, b = call(S4, "GET", f"/series/{src_sid}", token=ada)
    expect("X-s3-4a", st == 200
           and (j(b) or {}).get("series_id") == src_sid,
           f"imported series {src_sid} visible st={st}")
    st, hd, b = call(S4, "GET", "/restaurants/r_ops/policies")
    expect("X-s3-4b", st == 200
           and len((j(b) or {}).get("policies", [])) >= 1,
           "imported policy visible")
    # X-4b: no phantom closures — t_a/t_b still bookable at a fresh time
    free = utc_local(600)
    opts = avail_opts("r_ops", free[:10], 2, free)
    expect("X-s3-4c", opts is not None and ["t_a"] in opts
           and ["t_b"] in opts,
           f"no phantom closures post-import {opts}")

    # ---- leg D: stage-4 round-trip preserves plans + closures ----
    fx = fixture_3()
    st, hd, b = call(S4, "POST", "/_test/reset", body=fx)
    expect("X-s4-0", st == 204, f"s4 reset st={st}")
    st, ada = _login(S4)
    base = dt_utc(500)
    T1 = base.strftime("%Y-%m-%dT%H:%M")
    st, hd, b = call(S4, "POST", "/reservations", token=ada, idem="s4-k1",
                     body={"restaurant_id": "r_ops", "table_id": "t_a",
                           "starts_at_local": T1, "party_size": 2})
    ref = (j(b) or {}).get("reference")
    expect("X-s4-1", st == 201 and ref, f"s4 booking st={st}")
    # apply a closure on t_b (leaves ref on t_a alone)
    st, hd, b = call(S4, "POST", "/restaurants/r_ops/replans",
                     token=ada, idem="s4-p1",
                     body={"table_id": "t_b",
                           "from": iso(base),
                           "to": iso(base + timedelta(hours=2))})
    pid_applied = (j(b) or {}).get("plan_id")
    st, hd, b = call(S4, "POST",
                     f"/restaurants/r_ops/replans/{pid_applied}/apply",
                     token=ada, idem="s4-ap1", body={})
    expect("X-s4-2", st == 201, f"apply closure st={st}")
    # a still-PENDING plan on t_a later in the day
    st, hd, b = call(S4, "POST", "/restaurants/r_ops/replans",
                     token=ada, idem="s4-p2",
                     body={"table_id": "t_a",
                           "from": iso(base + timedelta(hours=6)),
                           "to": iso(base + timedelta(hours=8))})
    pid_pending = (j(b) or {}).get("plan_id")
    expect("X-s4-3", st == 201 and pid_pending, f"pending plan st={st}")
    st, hd, b = call(S4, "POST", "/series", token=ada, idem="s4-ser",
                     body={"anchor_reference": ref, "count": 2,
                           "interval_weeks": 1})
    expect("X-s4-4", st == 201, f"series st={st}")
    sid = (j(b) or {}).get("series_id")
    def snap():
        out = {}
        st, hd, b = call(S4, "GET", f"/series/{sid}", token=ada)
        out["series"] = j(b)
        st, hd, b = call(S4, "GET", f"/reservations/{ref}/history",
                         token=ada)
        out["hist"] = j(b)
        st, hd, b = call(S4, "GET", "/_test/export")
        out["export"] = j(b)
        return out
    pre = snap()
    exp = pre["export"]
    stt = (exp or {}).get("state") or {}
    expect("X-s4-5", "plans" in stt and "closures" in stt,
           f"export exposes plans+closures keys {sorted(stt.keys())[:12]}")
    st2, hd2, b2 = call(S4, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s4-6a", st2 == 204, f"s4 self round-trip st={st2}")
    post = snap()
    expect("X-s4-6b", post["series"] == pre["series"],
           "series identical after s4 round-trip")
    expect("X-s4-6c", post["hist"] == pre["hist"],
           "history identical after s4 round-trip")
    def _strip_empty(v):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                sx = _strip_empty(x)
                if isinstance(sx, (dict, list)) and not sx:
                    continue  # container collapsed to empty after stripping
                out[k] = sx
            return out
        if isinstance(v, list):
            return [_strip_empty(x) for x in v]
        return v
    expect("X-s4-6d", _strip_empty(post["export"]) == _strip_empty(pre["export"]),
           "export identical after s4 round-trip (mod empty-coll normalisation)")
    # fixpoint: re-importing the post snapshot is a no-op
    call(S4, "POST", "/_test/import", raw=json.dumps(post["export"]))
    st, hd, b = call(S4, "GET", "/_test/export")
    expect("X-s4-6e", j(b) == post["export"],
           "export import round-trip reaches fixpoint")
    # applied closure still blocks AFTER the round-trip
    opts = avail_opts("r_ops", T1[:10], 2,
                      (base + timedelta(minutes=30))
                      .strftime("%Y-%m-%dT%H:%M"))
    expect("X-s4-7", opts is not None and ["t_b"] not in opts,
           f"imported closure still excludes t_b {opts}")
    st, hd, b = call(S4, "POST", "/reservations", token=ada, idem="s4-k2",
                     body={"restaurant_id": "r_ops", "table_id": "t_b",
                           "starts_at_local": (base + timedelta(minutes=30))
                           .strftime("%Y-%m-%dT%H:%M"), "party_size": 2})
    expect("X-s4-7b", st == 409
           and err_code(b) == "table_unavailable",
           f"create on imported closure st={st}")
    # pending plan still pending + applicable after the round-trip
    st, hd, b = call(S4, "POST",
                     f"/restaurants/r_ops/replans/{pid_pending}/apply",
                     token=ada, idem="s4-ap2", body={})
    expect("X-s4-8", st in (201, 409),
           f"imported pending plan apply st={st} {err_code(b)}")
    if st == 409:
        expect("X-s4-8b", err_code(b) == "stale_plan",
               "if stale, still a coherent plan state")
    else:
        expect("X-s4-8b", True, "pending plan applied post-import")

    # ---- X-5: invalid payloads leave destination unchanged ----
    pre2 = snap()
    for tag, raw in (
        ("wrong_track", b'{"track":"other","format_version":1,"state":{}}'),
        ("wrong_ver", b'{"track":"tablekeeper","format_version":9,"state":{}}'),
        ("no_state", b'{"track":"tablekeeper","format_version":1}')):
        st, hd, b = call(S4, "POST", "/_test/import", raw=raw)
        expect(f"X-5:{tag}", st == 422, f"st={st}")
    post2 = snap()
    expect("X-5b", post2["series"] == pre2["series"]
           and post2["export"] == pre2["export"],
           "state unchanged after bad imports")

    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} upgrade checks, {len(fails)} FAIL, "
          f"{time.monotonic()-t0:.1f}s ==")
    for c in fails:
        print("FAIL", c)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
