#!/usr/bin/env python3
"""tk-experience supplemental UI checks — exercises the sections the
verifier suite never reached after its own U-CMB-1 abort: combo booking
at a slot where the declared pair is genuinely free, lookup + cancel,
refused cancel, 375px no-hscroll, and export/import mid-pending-retry.

Run:  D:\\tk-official\\.venv\\Scripts\\python.exe ui_checks_experience.py \
        --base-url http://localhost:8091
"""
import argparse, json, pathlib, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8091"
RESULTS = []
TMO = 6000

def t(tid): return f'[data-testid="{tid}"]'
def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok)))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)

def call(method, path, body=None, token=None, idem=None, raw=None, timeout=15):
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": "application/json"} if data else {}
    if token: h["Authorization"] = "Bearer " + token
    if idem: h["Idempotency-Key"] = idem
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def j(b):
    try: return json.loads(b)
    except Exception: return None

def visible(page, tid, timeout=TMO):
    try:
        page.wait_for_selector(t(tid), state="visible", timeout=timeout)
        return True
    except Exception:
        return False

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def fixture():
    near = (datetime.now(timezone.utc) + timedelta(minutes=45))
    near = near.replace(minute=(near.minute // 30) * 30, second=0,
                        microsecond=0)
    if near.hour >= 22:
        near = near.replace(hour=20, minute=30)
    return {
        "users": [{"id": "u_a", "email": "xp@example.com",
                   "password": "password-xp-9", "display_name": "Xp Diner"}],
        "restaurants": [
            {"id": "r_x", "name": "Zum Anker", "timezone": "UTC",
             "slot_minutes": 30, "reservation_duration_minutes": 90,
             "cancellation_cutoff_minutes": 120,
             "opening_hours": [{"weekday": w, "opens": "10:00",
                                "closes": "22:00"} for w in DAYS],
             "combinable": [["t_win", "t_gar"]],
             "tables": [{"id": "t_win", "label": "Window Nook",
                         "capacity": 2},
                        {"id": "t_gar", "label": "Garden Table",
                         "capacity": 4}]},
        ],
        "reservations": [
            {"id": "rs_near", "reference": "NEAR01", "user_id": "u_a",
             "restaurant_id": "r_x", "table_id": "t_win",
             "starts_at_local": near.strftime("%Y-%m-%dT%H:%M"),
             "party_size": 2},
        ],
    }

def login(page):
    page.goto(BASE + "/login")
    page.fill(t("login-email"), "xp@example.com")
    page.fill(t("login-password"), "password-xp-9")
    page.click(t("login-submit"))
    page.wait_for_selector(t("current-user"), timeout=TMO)

def search(page, d, party):
    page.goto(BASE + "/")
    page.select_option(t("restaurant-select"), "r_x")
    page.fill(t("date-input"), d)
    page.fill(t("party-size-input"), str(party))
    page.click(t("search-button"))
    page.wait_for_selector(t("availability-grid"), state="visible",
                           timeout=TMO)

def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")

    st, hd, b = call("POST", "/_test/reset", body=fixture())
    if st != 204:
        print("reset failed", st, b[:200]); sys.exit(1)

    d0 = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%d")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(TMO)

        login(page)

        # --- combo booking at a free slot ---------------------------
        search(page, d0, 6)
        cmb = t("slot-t_win+t_gar-14:00")
        expect("X-CMB-1", page.locator(cmb).count() == 1,
               "combo cell present when pair free")
        expect("X-CMB-2",
               page.locator(cmb).get_attribute("data-available") == "true",
               "combo data-available true")
        page.click(cmb)
        summ = page.text_content(t("booking-summary")) or ""
        expect("X-CMB-3",
               "Window Nook" in summ and "Garden Table" in summ,
               f"summary {summ!r}")
        page.click(t("booking-submit"))
        expect("X-CMB-4", visible(page, "confirmation"), "combo booked")
        ref = (page.text_content(t("confirmation-reference")) or "").strip()
        tabs = page.text_content(t("confirmation-tables")) or ""
        expect("X-CMB-5", "Window Nook" in tabs and "Garden Table" in tabs,
               f"confirmation-tables {tabs!r}")
        st2, _, b2 = call("GET", "/reservations/" + ref,
                          token=None)  # check needs auth -> expect 401
        st2, _, b2 = call("POST", "/auth/login",
                         body={"email": "xp@example.com",
                               "password": "password-xp-9"})
        tok = (j(b2) or {}).get("token")
        st2, _, b2 = call("GET", "/reservations/" + ref, token=tok)
        body = j(b2) or {}
        expect("X-CMB-6", body.get("table_ids") == ["t_win", "t_gar"]
               and "table_id" not in body, f"pair stored {body.get('table_ids')}")

        # --- lookup: not-found, found, cancel, refused cancel ---------
        page.goto(BASE + "/lookup")
        page.fill(t("lookup-reference-input"), "ZZZ999")
        page.click(t("lookup-submit"))
        expect("X-LKP-1", visible(page, "reservation-error"), "not-found")
        page.fill(t("lookup-reference-input"), ref)
        page.click(t("lookup-submit"))
        expect("X-LKP-2", visible(page, "reservation-detail"), "found")
        stat = (page.text_content(t("reservation-status")) or "").strip()
        expect("X-LKP-3", stat == "confirmed", f"status {stat!r}")
        rt = page.text_content(t("reservation-tables")) or ""
        expect("X-LKP-4", "Window Nook" in rt and "Garden Table" in rt,
               f"reservation-tables {rt!r}")
        page.click(t("reservation-cancel-button"))
        try:
            page.wait_for_function(
                "document.querySelector('[data-testid=\"reservation-status\"]')"
                "?.textContent.trim() === 'cancelled'", timeout=TMO)
            stat2 = "cancelled"
        except Exception:
            stat2 = "stuck"
        expect("X-LKP-5", stat2 == "cancelled", "cancel flips status")
        gone = page.locator(t("reservation-cancel-button")).count() == 0
        expect("X-LKP-6", gone, "cancel button absent after cancel")
        page.fill(t("lookup-reference-input"), "NEAR01")
        page.click(t("lookup-submit"))
        page.wait_for_selector(t("reservation-detail"), timeout=TMO)
        page.click(t("reservation-cancel-button"))
        expect("X-LKP-7", visible(page, "reservation-error"),
               "refused cancel -> reservation-error")

        # --- pending retry survives export/import ---------------------
        search(page, d0, 2)
        page.wait_for_selector(t("slot-t_gar-16:00"), timeout=TMO)
        page.click(t("slot-t_gar-16:00"))
        page.wait_for_selector(t("booking-form"), timeout=TMO)
        fired = {"n": 0}
        def drop(route):
            if route.request.method == "POST" and not fired["n"]:
                fired["n"] = 1
                try: route.fetch()
                except Exception: pass
                route.abort()
            else:
                route.continue_()
        page.route(re.compile(r".*/reservations$"), drop)
        page.click(t("booking-submit"))
        expect("X-UPG-1", visible(page, "booking-uncertain"),
               "uncertain on dropped response")
        st, _, b = call("GET", "/_test/export")
        st2, _, _ = call("POST", "/_test/import", raw=b)
        expect("X-UPG-2", st == 200 and st2 == 204,
               f"export/import {st}/{st2}")
        cu = "Xp Diner" in (page.text_content(t("current-user")) or "")
        expect("X-UPG-3", cu, "session survives import")
        page.unroute(re.compile(r".*/reservations$"))
        page.click(t("booking-submit"))
        expect("X-UPG-4", visible(page, "confirmation"),
               "retry after import confirms")
        ref2 = (page.text_content(t("confirmation-reference")) or "").strip()
        _, _, b3 = call("GET", "/reservations", token=tok)
        mine = [r for r in (j(b3) or {}).get("reservations", [])
                if r.get("starts_at_local") == f"{d0}T16:00"]
        expect("X-UPG-5", len(mine) == 1 and mine[0]["reference"] == ref2,
               f"original ref recovered {ref2!r}")

        # --- 375px ----------------------------------------------------
        pg = browser.new_context(
            viewport={"width": 375, "height": 800}).new_page()
        pg.set_default_timeout(TMO)
        pg.goto(BASE + "/login")
        pg.fill(t("login-email"), "xp@example.com")
        pg.fill(t("login-password"), "password-xp-9")
        pg.click(t("login-submit"))
        pg.wait_for_selector(t("current-user"), timeout=TMO)
        for tag, path in (("login->", None), ("home", "/"), ):
            pass
        pg.goto(BASE + "/")
        sw = pg.evaluate("document.documentElement.scrollWidth")
        iw = pg.evaluate("window.innerWidth")
        expect("X-VP-home", sw <= iw + 1, f"{sw} vs {iw}")
        pg.select_option(t("restaurant-select"), "r_x")
        pg.fill(t("date-input"), d0)
        pg.fill(t("party-size-input"), "2")
        pg.click(t("search-button"))
        pg.wait_for_selector(t("availability-grid"), state="visible",
                             timeout=TMO)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        expect("X-VP-grid", sw <= iw + 1, f"{sw} vs {iw}")
        pg.click(t("slot-t_gar-10:00"))
        pg.wait_for_selector(t("booking-form"), timeout=TMO)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        expect("X-VP-form", sw <= iw + 1, f"{sw} vs {iw}")
        pg.close()

        ctx.close(); browser.close()

    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} supplemental checks, {len(fails)} FAIL ==")
    for c in fails: print("FAIL", c)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
