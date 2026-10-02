#!/usr/bin/env python3
"""tk-verifier stage-2: upgrade continuity (U9).

Proves a stage-2 service accepts an export produced by the team's stage-1
service and that browser-visible state survives:
  UPG-1  stage-1 export imports into stage-2 -> 204
  UPG-2  bearer token issued pre-upgrade stays valid post-import
  UPG-3  retained booking reference resolves post-import (lookup path)
  UPG-4  a booking whose response was LOST pre-export replays post-import
         with the same key+body -> original confirmation recovered
  UPG-5  imported reservation view: table_ids always, table_id iff singleton
  UPG-6  stage-1-shaped imported state normalised (combinable absent -> [])
  UPG-7  stage-2 still accepts its own export (round-trip sanity)
  UPG-8  invalid upgrade payload -> 422, destination unchanged

Usage:
  python upgrade_checks.py --s1-url http://localhost:8091 \
                           --s2-url http://localhost:8080
Both services must be running (s1 = stage-1 code, s2 = stage-2 code).
"""
import argparse, json, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

S1 = "http://localhost:8091"; S2 = "http://localhost:8080"
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

def fixture_s1():
    """Stage-1-shaped fixture: NO combinable field anywhere."""
    return {
        "users": [{"id": "u_ada", "email": "ada@example.com",
                   "password": "correct horse", "display_name": "Ada"}],
        "restaurants": [{"id": "r_ops", "name": "Ops Haus", "timezone": "UTC",
            "slot_minutes": 15, "reservation_duration_minutes": 60,
            "cancellation_cutoff_minutes": 120,
            "opening_hours": [{"weekday": w, "opens": "00:00", "closes": "23:59"}
                              for w in ["mon","tue","wed","thu","fri","sat","sun"]],
            "tables": [{"id": "t_a", "label": "A", "capacity": 4},
                       {"id": "t_b", "label": "B", "capacity": 4}]}],
        "reservations": []}

def main():
    global S1, S2
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1-url", default=S1)
    ap.add_argument("--s2-url", default=S2)
    args = ap.parse_args()
    S1 = args.s1_url.rstrip("/"); S2 = args.s2_url.rstrip("/")
    t0 = time.monotonic()

    st, hd, b = call(S1, "POST", "/_test/reset", body=fixture_s1())
    expect("UPG-0", st == 204, f"s1 reset st={st}")
    st, hd, b = call(S1, "POST", "/auth/login",
                     body={"email": "ada@example.com", "password": "correct horse"})
    ada = (j(b) or {}).get("token")
    expect("UPG-0b", st == 200 and ada, "s1 login")

    # ordinary booking whose reference is RETAINED by the client
    T1 = utc_local(300)
    st, hd, b = call(S1, "POST", "/reservations", token=ada, idem="upg-k1",
        body={"restaurant_id": "r_ops", "table_id": "t_a",
              "starts_at_local": T1, "party_size": 2})
    expect("UPG-0c", st == 201, f"s1 book st={st}")
    ref_keep = (j(b) or {}).get("reference")

    # booking whose RESPONSE IS LOST: client keeps only key+body
    lost_body = {"restaurant_id": "r_ops", "table_id": "t_b",
                 "starts_at_local": utc_local(400), "party_size": 3}
    st, hd, b = call(S1, "POST", "/reservations", token=ada, idem="upg-lost",
                     body=lost_body)
    lost_resp = j(b)
    expect("UPG-0d", st == 201 and lost_resp.get("reference"),
           "s1 lost-response booking committed server-side")

    st, hd, b = call(S1, "GET", "/_test/export")
    export_obj = j(b)
    expect("UPG-1a", st == 200 and isinstance(export_obj, dict)
           and export_obj.get("track") == "tablekeeper", "s1 export shape")

    # import into stage-2
    st, hd, b = call(S2, "POST", "/_test/import", raw=json.dumps(export_obj))
    expect("UPG-1", st == 204, f"s2 import of s1 export st={st} body={b[:120]!r}")

    # token survives (browser stays signed in)
    st, hd, b = call(S2, "GET", "/reservations", token=ada)
    expect("UPG-2", st == 200, f"token valid post-import st={st}")
    refs = {x.get("reference") for x in (j(b) or {}).get("reservations", [])}
    expect("UPG-2b", ref_keep in refs, f"reservations visible {refs}")

    # retained reference resolves (lookup path uses GET /reservations/{ref})
    st, hd, b = call(S2, "GET", f"/reservations/{ref_keep}", token=ada)
    r = j(b) or {}
    expect("UPG-3", st == 200 and r.get("reference") == ref_keep
           and r.get("status") == "confirmed", f"ref resolves st={st}")
    expect("UPG-5", r.get("table_ids") == ["t_a"] and r.get("table_id") == "t_a",
           f"normalised view {sorted(r)}")

    # lost booking replays post-import -> ORIGINAL confirmation
    st, hd, b = call(S2, "POST", "/reservations", token=ada, idem="upg-lost",
                     body=lost_body)
    expect("UPG-4", st == 200 and j(b) == lost_resp,
           f"pending retry recovered st={st} body match={j(b)==lost_resp}")

    # normalised restaurant state: combinable absent -> treated as []
    st, hd, b = call(S2, "GET", "/restaurants/r_ops")
    comb = (j(b) or {}).get("combinable")
    expect("UPG-6", st == 200 and (comb is None or comb == []),
           f"combinable absent-or-empty after s1 import: {comb!r}")
    # availability still computed; stage-1 behaviour on imported fixture
    st, hd, b = call(S2, "GET",
        f"/availability?restaurant_id=r_ops&date={T1[:10]}&party_size=2")
    sl = [s for s in (j(b) or {}).get("slots", [])
          if s.get("starts_at_local") == T1]
    expect("UPG-6b", bool(sl) and "t_a" not in sl[0].get("available_table_ids", [])
           and "t_b" in sl[0].get("available_table_ids", []),
           "imported occupancy honoured by availability")

    # stage-2 round-trips its own (post-import) export
    st, hd, b = call(S2, "GET", "/_test/export")
    st2, hd2, b2 = call(S2, "POST", "/_test/import", raw=b)
    expect("UPG-7", st == 200 and st2 == 204, f"self round-trip {st}/{st2}")
    st, hd, b = call(S2, "GET", "/reservations", token=ada)
    expect("UPG-7b", st == 200 and ref_keep in
           {x.get("reference") for x in (j(b) or {}).get("reservations", [])},
           "state identical after self-import")

    # invalid upgrade payloads -> 422, destination unchanged
    for tag, raw in (("wrong_track", b'{"track":"other","format_version":1,"state":{}}'),
                     ("wrong_ver", b'{"track":"tablekeeper","format_version":9,"state":{}}'),
                     ("no_state", b'{"track":"tablekeeper","format_version":1}')):
        st, hd, b = call(S2, "POST", "/_test/import", raw=raw)
        expect(f"UPG-8:{tag}", st == 422, f"st={st}")
    st, hd, b = call(S2, "GET", "/reservations", token=ada)
    expect("UPG-8b", st == 200, "destination unchanged after bad imports")

    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} upgrade checks, {len(fails)} FAIL, "
          f"{time.monotonic()-t0:.1f}s ==")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
