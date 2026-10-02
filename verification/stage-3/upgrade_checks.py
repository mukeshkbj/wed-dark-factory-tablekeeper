#!/usr/bin/env python3
"""tk-verifier stage-3: upgrade/import continuity (X).

Proves a stage-3 service accepts exports produced by the team's stage-1 or
stage-2 service, that imported reservations are adoptable into series, and
that stage-3 state (policies, series, histories, revisions, terms) survives
an export/import round-trip:

  X-1  stage-1 and stage-2 exports both import into stage-3 -> 204
  X-2  an imported reservation can be adopted as series anchor
  X-3  pre-upgrade tokens, references and pending retries stay valid
  X-4  imported reservations normalise to revision 1 + policy-0 terms;
       history/decision endpoints serve them
  X-5  failed import leaves destination state untouched
  X-6  stage-3 export round-trips policies/series/history/terms intact

Usage:
  python upgrade_checks.py --s1-url ... --s2-url ... --s3-url ...
All three services must be running (s1, s2, s3 code respectively).
"""
import argparse, json, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

S1 = "http://localhost:8091"; S2 = "http://localhost:8092"
S3 = "http://localhost:8093"
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

def utc_local(minutes_from_now):
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    dt = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
    if dt.hour >= 23: dt = dt.replace(hour=22, minute=45)
    return dt.strftime("%Y-%m-%dT%H:%M")

WEEK = ["mon","tue","wed","thu","fri","sat","sun"]

def fixture_1():
    """Stage-1-shaped fixture: no combinable, no managers."""
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
    """Stage-2-shaped fixture: combinable pairs, no managers."""
    fx = fixture_1()
    fx["restaurants"][0]["combinable"] = [["t_a", "t_b"]]
    return fx

def _prep_source(base, fx, tag):
    """Reset source, login, make a kept booking and a 'lost response' booking."""
    st, hd, b = call(base, "POST", "/_test/reset", body=fx)
    expect(f"X-{tag}-0", st == 204, f"source reset st={st}")
    st, hd, b = call(base, "POST", "/auth/login",
                     body={"email": "ada@example.com",
                           "password": "correct horse"})
    ada = (j(b) or {}).get("token")
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
    expect(f"X-{tag}-0d", st == 201 and lost.get("reference"),
           "lost-response booking committed")
    st, hd, b = call(base, "GET", "/_test/export")
    exp = j(b)
    expect(f"X-{tag}-0e", st == 200 and isinstance(exp, dict)
           and exp.get("track") == "tablekeeper", "source export shape")
    return ada, keep, lost, lost_body, exp

def _check_imported(tag, ada, keep, lost, lost_body):
    """After import into stage-3: normalisation + continuity."""
    st, hd, b = call(S3, "GET", "/reservations", token=ada)
    expect(f"X-{tag}-3a", st == 200, f"token survives st={st}")
    refs = {x.get("reference") for x in (j(b) or {}).get("reservations", [])}
    expect(f"X-{tag}-3b", keep.get("reference") in refs
           and lost.get("reference") in refs, f"refs visible {refs}")
    # X-4: normalised to revision 1 + policy-0 accepted terms
    st, hd, b = call(S3, "GET", f"/reservations/{keep['reference']}",
                     token=ada)
    r = j(b) or {}
    terms = r.get("accepted_terms") or {}
    expect(f"X-{tag}-4a", st == 200 and r.get("revision") == 1
           and terms.get("policy_version") == 0
           and terms.get("capacities") == {"t_a": 4, "t_b": 4},
           f"normalised rev/terms {r.get('revision')} {terms.get('policy_version')}")
    st, hd, b = call(S3, "GET", f"/reservations/{keep['reference']}/history",
                     token=ada)
    ent = (j(b) or {}).get("entries") or []
    expect(f"X-{tag}-4b", st == 200 and len(ent) >= 1
           and ent[0].get("event") == "created",
           f"imported history reconstructed n={len(ent)}")
    st, hd, b = call(S3, "GET", f"/reservations/{keep['reference']}/decision",
                     token=ada)
    expect(f"X-{tag}-4c", st == 200
           and (j(b) or {}).get("revision") == 1, "decision on import")
    # X-3: pending retry recovers the ORIGINAL confirmation
    st, hd, b = call(S3, "POST", "/reservations", token=ada,
                     idem=f"upg-{tag}-lost", body=lost_body)
    expect(f"X-{tag}-3c", st == 200 and j(b) == lost,
           f"lost retry recovered st={st}")
    # X-2: imported reservation is adoptable into a series
    st, hd, b = call(S3, "POST", "/series", token=ada, idem=f"upg-{tag}-ser",
                     body={"anchor_reference": keep["reference"],
                           "count": 2, "interval_weeks": 1})
    expect(f"X-{tag}-2", st == 201, f"adopt imported st={st} {b[:120]!r}")

def main():
    global S1, S2, S3
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1-url", default=S1)
    ap.add_argument("--s2-url", default=S2)
    ap.add_argument("--s3-url", default=S3)
    args = ap.parse_args()
    S1 = args.s1_url.rstrip("/"); S2 = args.s2_url.rstrip("/")
    S3 = args.s3_url.rstrip("/")
    t0 = time.monotonic()

    # ---- leg A: stage-1 source -> stage-3 ----
    ada, keep, lost, lost_body, exp = _prep_source(S1, fixture_1(), "s1")
    st, hd, b = call(S3, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s1-1", st == 204, f"s1 export -> s3 import st={st}")
    _check_imported("s1", ada, keep, lost, lost_body)

    # ---- leg B: stage-2 source -> stage-3 ----
    ada, keep, lost, lost_body, exp = _prep_source(S2, fixture_2(), "s2")
    st, hd, b = call(S3, "POST", "/_test/import", raw=json.dumps(exp))
    expect("X-s2-1", st == 204, f"s2 export -> s3 import st={st}")
    _check_imported("s2", ada, keep, lost, lost_body)

    # ---- leg C: stage-3 round-trip preserves new state ----
    # fixture_2 plus a manager so we can publish a policy
    fx = fixture_2()
    fx["restaurants"][0]["manager_user_ids"] = ["u_ada"]
    st, hd, b = call(S3, "POST", "/_test/reset", body=fx)
    expect("X-s3-0", st == 204, f"s3 reset st={st}")
    st, hd, b = call(S3, "POST", "/auth/login",
                     body={"email": "ada@example.com",
                           "password": "correct horse"})
    ada = (j(b) or {}).get("token")
    T1 = utc_local(500)
    st, hd, b = call(S3, "POST", "/reservations", token=ada, idem="s3-k1",
                     body={"restaurant_id": "r_ops", "table_id": "t_a",
                           "starts_at_local": T1, "party_size": 2})
    ref = (j(b) or {}).get("reference")
    pol = {"effective_from": "2026-10-01", "slot_minutes": 15,
           "reservation_duration_minutes": 30, "cancellation_cutoff_minutes": 60,
           "opening_hours": [{"weekday": w, "opens": "00:00",
                              "closes": "23:59"} for w in WEEK],
           "capacities": {"t_a": 4, "t_b": 4}}
    st, hd, b = call(S3, "POST", "/restaurants/r_ops/policies",
                     token=ada, idem="s3-pol", body=pol)
    expect("X-s3-1", st == 201, f"policy publish st={st}")
    st, hd, b = call(S3, "POST", "/series", token=ada, idem="s3-ser",
                     body={"anchor_reference": ref, "count": 3,
                           "interval_weeks": 1})
    expect("X-s3-2", st == 201, f"series st={st}")
    S = j(b) or {}
    sid = S.get("series_id")
    occ_refs = [o.get("reference") for o in S.get("occurrences", [])]
    call(S3, "PATCH", f"/reservations/{occ_refs[1]}", token=ada,
         body={"party_size": 3})                    # exception
    call(S3, "POST", f"/reservations/{occ_refs[2]}/cancel", token=ada)
    # snapshot pre-export state
    st, hd, b = call(S3, "GET", f"/series/{sid}", token=ada)
    pre_series = j(b)
    st, hd, b = call(S3, "GET", "/restaurants/r_ops/policies")
    pre_pols = j(b)
    st, hd, b = call(S3, "GET", f"/reservations/{ref}/history", token=ada)
    pre_hist = j(b)
    # export -> import round-trip
    st, hd, b = call(S3, "GET", "/_test/export")
    exp = j(b)
    st2, hd2, b2 = call(S3, "POST", "/_test/import", raw=b)
    expect("X-s3-6a", st == 200 and st2 == 204, f"round-trip {st}/{st2}")
    st, hd, b = call(S3, "GET", f"/series/{sid}", token=ada)
    expect("X-s3-6b", j(b) == pre_series,
           "series state identical after round-trip")
    st, hd, b = call(S3, "GET", "/restaurants/r_ops/policies")
    expect("X-s3-6c", j(b) == pre_pols, "policies identical after round-trip")
    st, hd, b = call(S3, "GET", f"/reservations/{ref}/history", token=ada)
    expect("X-s3-6d", j(b) == pre_hist, "history identical after round-trip")
    st, hd, b = call(S3, "GET", f"/reservations/{ref}/decision", token=ada)
    expect("X-s3-6e", st == 200, "decision survives round-trip")

    # ---- X-5: invalid payloads leave destination unchanged ----
    for tag, raw in (("wrong_track", b'{"track":"other","format_version":1,"state":{}}'),
                     ("wrong_ver", b'{"track":"tablekeeper","format_version":9,"state":{}}'),
                     ("no_state", b'{"track":"tablekeeper","format_version":1}')):
        st, hd, b = call(S3, "POST", "/_test/import", raw=raw)
        expect(f"X-5:{tag}", st == 422, f"st={st}")
    st, hd, b = call(S3, "GET", f"/series/{sid}", token=ada)
    expect("X-5b", j(b) == pre_series, "state unchanged after bad imports")

    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} upgrade checks, {len(fails)} FAIL, "
          f"{time.monotonic()-t0:.1f}s ==")
    for c in fails:
        print("FAIL", c)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
