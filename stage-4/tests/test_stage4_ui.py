#!/usr/bin/env python3
"""tk-experience stage-4 focused check (D-5/R4-24) — the inherited
browser surface must reflect an applied closure replan with no UI
changes.

Flow: reset the managed demo seed -> preview + apply a closure on
`t_counter` through the manager API -> verify in the real browser that
the existing search grid marks the closed table unavailable, marks the
reassigned table occupied by the moved booking, scopes the closure to
its interval, and that /lookup shows the moved booking on its new table.

Run against a running stage-4 server:
    python tests/test_stage4_ui.py --base-url http://localhost:8152
"""
import argparse, json, os, sys, urllib.request, urllib.error

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import fixtures  # noqa: E402

BASE = "http://localhost:8080"
RESULTS = []
TMO = 6000


def t(tid):
    return f'[data-testid="{tid}"]'


def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok)))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)


def call(method, path, body=None, token=None, idem=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    if token:
        h["Authorization"] = "Bearer " + token
    if idem:
        h["Idempotency-Key"] = idem
    r = urllib.request.Request(BASE + path, data=data, headers=h,
                               method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def login(page, email, password):
    page.goto(BASE + "/login")
    page.fill(t("login-email"), email)
    page.fill(t("login-password"), password)
    page.click(t("login-submit"))
    page.wait_for_selector(t("current-user"), state="visible",
                           timeout=TMO)


def search(page, rid, date_str, party):
    page.goto(BASE + "/")
    page.wait_for_selector(t("restaurant-select") + " option",
                           state="attached", timeout=TMO)
    page.select_option(t("restaurant-select"), rid)
    page.fill(t("date-input"), date_str)
    page.fill(t("party-size-input"), str(party))
    page.click(t("search-button"))
    # OR-selector wait like the official harness: first DOM-order match
    # of grid/no-slots must resolve the visible applicable element.
    page.wait_for_selector(
        '[data-testid="availability-grid"], [data-testid="no-slots"]',
        state="visible", timeout=TMO)


def cell_available(page, tid, hhmm):
    loc = page.locator(t(f"slot-{tid}-{hhmm}"))
    if loc.count() != 1:
        return None
    return loc.get_attribute("data-available")


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")

    # --- API: managed demo data + closure preview/apply --------------
    st, b = call("POST", "/_test/reset", body=fixtures.demo_seed())
    if st != 204:
        print("reset failed", st, b)
        sys.exit(1)
    expect("S4-RESET", st == 204, "demo_seed reset")

    st, b = call("POST", "/auth/login", body={
        "email": "ines@tablekeeper.test", "password": "ines-pass-789"})
    manager = b.get("token")
    expect("S4-MGR", st == 200 and manager, "manager login")

    # ANK3R9 sits on t_counter 2026-10-02T19:30..21:00 Europe/Berlin.
    closure = {"table_id": "t_counter",
               "from": "2026-10-02T18:00:00+02:00",
               "to": "2026-10-02T23:00:00+02:00"}
    st, plan = call("POST", "/restaurants/r_anker/replans",
                    token=manager, idem="s4-replan-1", body=closure)
    expect("S4-PREVIEW", st == 201 and plan.get("plan_id"),
           f"preview {st}")
    moved = None
    for a in (plan or {}).get("assignments", []):
        if a["reference"] == "ANK3R9":
            moved = a["table_ids"]
            expect("S4-ASSIGN", a["changed"] and "t_counter" not in
                   a["table_ids"], f"ANK3R9 -> {a['table_ids']}")
    if not moved:
        expect("S4-ASSIGN", False, "ANK3R9 missing from plan")
        moved = ["t_alcove"]
    seed = fixtures.demo_seed()
    labels = {tb["id"]: tb.get("label", tb["id"])
              for r in seed["restaurants"] for tb in r["tables"]}
    moved_labels = [labels[tid] for tid in moved]

    st, applied = call(
        "POST", f"/restaurants/r_anker/replans/{plan['plan_id']}/apply",
        token=manager, idem="s4-apply-1", body={})
    expect("S4-APPLY", st == 201 and applied.get("reservations"),
           f"apply {st}")

    # --- Browser: inherited surfaces reflect the applied plan --------
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(
            viewport={"width": 1366, "height": 900}).new_page()
        page.set_default_timeout(TMO)

        login(page, "demo@tablekeeper.test", "demo-pass-123")
        expect("S4-LOGIN", "Demo Diner" in
               (page.text_content(t("current-user")) or ""),
               "current-user shows diner")

        # Search the closure day: grid renders (OR-selector resolves
        # the visible grid, not a hidden no-slots node).
        search(page, "r_anker", "2026-10-02", 2)
        expect("S4-GRID",
               page.locator(t("availability-grid")).count() == 1
               and page.locator(t("no-slots")).count() == 0,
               "grid visible, no-slots absent")
        expect("S4-CLOSED",
               cell_available(page, "t_counter", "19:30") == "false",
               "closed table unavailable at 19:30")
        expect("S4-MOVED",
               cell_available(page, moved[0], "19:30") == "false",
               f"moved booking occupies {moved[0]}")
        expect("S4-FREE",
               cell_available(page, "t_window", "19:30") == "true",
               "unaffected table still free")

        # Closure is interval-scoped: t_counter bookable on other days.
        search(page, "r_anker", "2026-10-03", 2)
        expect("S4-SCOPED",
               cell_available(page, "t_counter", "21:00") == "true",
               "t_counter free outside closure window")

        # Lookup reflects the reassignment with status + new labels.
        page.goto(BASE + "/lookup")
        page.fill(t("lookup-reference-input"), "ANK3R9")
        page.click(t("lookup-submit"))
        page.wait_for_selector(t("reservation-detail"), state="visible",
                               timeout=TMO)
        stat = (page.text_content(t("reservation-status")) or "").strip()
        tabs = page.text_content(t("reservation-tables")) or ""
        expect("S4-LKP-STATUS", stat == "confirmed", f"status {stat!r}")
        expect("S4-LKP-TABLES",
               all(lb in tabs for lb in moved_labels)
               and labels["t_counter"] not in tabs,
               f"reservation-tables {tabs!r} want {moved_labels}")

        browser.close()

    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} stage-4 UI checks, {len(fails)} FAIL ==")
    for c in fails:
        print("FAIL", c)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
