#!/usr/bin/env python3
r"""tk-verifier stage-2: browser checks (Playwright chromium, sync API).

Covers spec UI clauses U1-U9 + C5: routes, testids, availability grid vs API
cross-check, booking lifecycle (resubmit replay, field-change new request),
thief-between-open-and-submit (409), dropped-response uncertainty + same-key
retry, out-of-order search, combo cells/labels, lookup+cancel flows,
signed-out gate, 375px sweep, and import-between-requests session survival.

Run with the harness venv (playwright installed):
  D:\tk-official\.venv\Scripts\python.exe ui_checks.py --base-url http://localhost:8080
Screenshots of named states -> --shots dir (default <repo>/evidence/raw/ui-s2).
Every wait is bounded; an error or hang is a FAIL.
"""
import argparse, json, pathlib, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8080"
SHOTS = None
RESULTS = []
TMO_MS = 6000

def t(tid):
    return f'[data-testid="{tid}"]'

def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok)))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)

def note(cid, detail):
    print("NOTE", cid, "-", detail, flush=True)

def shot(page, name):
    if SHOTS:
        try:
            page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
        except Exception as e:
            note("shot", f"{name}: {e!r}")

def call(method, path, body=None, raw=None, token=None, idem=None, timeout=15):
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode()
    else:
        data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
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

def local30(minutes_from_now):
    """UTC wall clock snapped to r_ui's 30-minute grid."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    dt = dt.replace(minute=(dt.minute // 30) * 30, second=0, microsecond=0)
    if dt.hour >= 22:
        dt = dt.replace(hour=20, minute=30)
    return dt.strftime("%Y-%m-%dT%H:%M")

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def fixture_ui(near_local):
    """near_local: a starts_at_local inside the cancel cutoff (r_ui tz = UTC)."""
    return {
        "users": [
            {"id": "u_demo", "email": "demo@example.com",
             "password": "password-demo-9", "display_name": "Demo Diner"},
            {"id": "u_thief", "email": "thief@example.com",
             "password": "password-thief-9", "display_name": "Thief"},
        ],
        "restaurants": [
            {"id": "r_ui", "name": "Zum Anker", "timezone": "UTC",
             "slot_minutes": 30, "reservation_duration_minutes": 90,
             "cancellation_cutoff_minutes": 120,
             "opening_hours": [{"weekday": w, "opens": "10:00", "closes": "22:00"}
                               for w in DAYS],
             "combinable": [["t_win", "t_gar"], ["t_gar", "t_pat"]],
             "tables": [{"id": "t_win", "label": "Window Nook", "capacity": 2},
                        {"id": "t_gar", "label": "Garden Table", "capacity": 4},
                        {"id": "t_pat", "label": "Patio Set", "capacity": 4}]},
            {"id": "r_closed", "name": "Nacht Bar", "timezone": "UTC",
             "slot_minutes": 30, "reservation_duration_minutes": 90,
             "cancellation_cutoff_minutes": 120,
             "opening_hours": [{"weekday": "wed", "opens": "18:00", "closes": "23:00"}],
             "tables": [{"id": "t_n1", "label": "Vault", "capacity": 4}]},
        ],
        "reservations": [
            {"id": "rs_near", "reference": "NEAR01", "user_id": "u_demo",
             "restaurant_id": "r_ui", "table_id": "t_pat",
             "starts_at_local": near_local, "party_size": 2},
        ],
    }

def has(page, tid, timeout=TMO_MS):
    try:
        page.wait_for_selector(t(tid), state="attached", timeout=timeout)
        return True
    except Exception:
        return False

def visible(page, tid, timeout=TMO_MS):
    try:
        page.wait_for_selector(t(tid), state="visible", timeout=timeout)
        return True
    except Exception:
        return False

def ui_signup(page, email, pw, name):
    page.goto(BASE + "/signup")
    page.fill(t("signup-email"), email)
    page.fill(t("signup-password"), pw)
    page.fill(t("signup-display-name"), name)
    page.click(t("signup-submit"))

def ui_login(page, email, pw):
    page.goto(BASE + "/login")
    page.fill(t("login-email"), email)
    page.fill(t("login-password"), pw)
    page.click(t("login-submit"))

def ui_search(page, restaurant_id, date_str, party):
    page.goto(BASE + "/")
    page.select_option(t("restaurant-select"), restaurant_id)
    page.fill(t("date-input"), date_str)
    page.fill(t("party-size-input"), str(party))
    page.click(t("search-button"))

def sec_routes(page):
    for p in ("/", "/signup", "/login", "/lookup"):
        st, hd, b = call("GET", p)
        ct = hd.get("Content-Type") or hd.get("content-type") or ""
        expect(f"U-RT:{p}", st == 200 and "text/html" in ct.lower(),
               f"st={st} ct={ct!r}")
    # other screens reachable through the UI: each route links onward
    page.goto(BASE + "/")
    nav = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))")
    ok = any(h and h.rstrip("/") in ("", "/lookup", "/login", "/signup") or
             h in ("/", "/lookup", "/login", "/signup") for h in nav)
    expect("U-RT-nav", ok, f"nav hrefs {nav}")

def sec_testids(page):
    page.goto(BASE + "/signup")
    for tid in ("signup-email", "signup-password", "signup-display-name",
                "signup-submit"):
        expect(f"U-TID:{tid}", has(page, tid), tid)
    page.goto(BASE + "/login")
    for tid in ("login-email", "login-password", "login-submit"):
        expect(f"U-TID:{tid}", has(page, tid), tid)
    expect("U-TID:auth-error-absent", not visible(page, "auth-error", 800),
           "auth-error absent on fresh login")
    page.goto(BASE + "/")
    for tid in ("restaurant-select", "date-input", "party-size-input",
                "search-button"):
        expect(f"U-TID:{tid}", has(page, tid), tid)
    page.goto(BASE + "/lookup")
    for tid in ("lookup-reference-input", "lookup-submit"):
        expect(f"U-TID:{tid}", has(page, tid), tid)

def sec_auth(page):
    ui_signup(page, "ui-signup@example.com", "password-ui-9", "UI User")
    ok = visible(page, "current-user") and \
         "UI User" in (page.text_content(t("current-user")) or "")
    expect("U-AU-1", ok, "current-user after signup with display name")
    for p in ("/", "/lookup", "/login", "/signup"):
        page.goto(BASE + p)
        ok = visible(page, "current-user") and \
             "UI User" in (page.text_content(t("current-user")) or "")
        expect(f"U-AU-2:{p}", ok, "current-user on every screen")
    # logout removes the session UI
    page.goto(BASE + "/")
    page.click(t("logout-button"))
    gone = True
    try:
        page.wait_for_selector(t("current-user"), state="detached", timeout=TMO_MS)
    except Exception:
        gone = not visible(page, "current-user", 500)
    expect("U-AU-3", gone, "logout removes current-user")
    # login with bad creds -> auth-error appears only then
    page.goto(BASE + "/login")
    page.fill(t("login-email"), "demo@example.com")
    page.fill(t("login-password"), "wrong-password")
    page.click(t("login-submit"))
    expect("U-AU-4", visible(page, "auth-error"), "auth-error on bad login")
    # real login
    ui_login(page, "demo@example.com", "password-demo-9")
    ok = visible(page, "current-user") and \
         "Demo Diner" in (page.text_content(t("current-user")) or "")
    expect("U-AU-5", ok, "login -> current-user")

def api_slots(rid, date_str, ps):
    st, hd, b = call("GET",
        f"/availability?restaurant_id={rid}&date={date_str}&party_size={ps}")
    return (j(b) or {}).get("slots", [])


def first_or_visible(page):
    """First element IN DOM ORDER matching the grid/no-slots OR-selector,
    and whether it is visible. Mirrors the official harness wait
    wait_for_selector("availability-grid, no-slots"), which locks onto the
    first DOM match and waits for ITS visibility — an always-present hidden
    element ahead of the grid in DOM order silently breaks that wait."""
    return page.evaluate(
        "var e=document.querySelector('[data-testid=\"availability-grid\"],"
        "[data-testid=\"no-slots\"]');"
        "e ? {tid:e.getAttribute('data-testid'),"
        "vis:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)}"
        " : null")

def or_wait_settles(page, want_tid):
    """Emulate wait_for_selector('grid, no-slots', state=visible): poll
    until the OR-selector wait resolves, then return the FIRST DOM match and
    whether it is the expected visible element. A hidden first match hangs
    the official harness (it proceeds with the first resolved element), so
    settling requires the inapplicable element to be absent or visible."""
    OR_SEL = ('[data-testid="availability-grid"],'
              '[data-testid="no-slots"]')
    try:
        page.wait_for_selector(OR_SEL, state="visible", timeout=TMO_MS)
    except Exception:
        return {"tid": None, "vis": False, "timeout": True}
    f = first_or_visible(page)
    if f:
        f["vis"] = f["vis"] and f["tid"] == want_tid
    return f

def cell_tid(tid_, hhmm):
    return f"slot-{tid_}-{hhmm}"

def combo_tid(a, b, hhmm):
    return f"slot-{a}+{b}-{hhmm}"

def sec_grid(page, ctx_api):
    """Cross-check the rendered grid cell-for-cell against the API."""
    ui_login(page, "demo@example.com", "password-demo-9")
    page.wait_for_selector(t("current-user"), state="visible", timeout=TMO_MS)
    d0 = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
    ui_search(page, "r_ui", d0, 2)
    ok = visible(page, "availability-grid")
    expect("U-GRID-1", ok, "grid renders after search")
    shot(page, "grid")
    slots = api_slots("r_ui", d0, 2)
    tables = ["t_win", "t_gar", "t_pat"]
    miss, mism = [], []
    for s_ in slots:
        hhmm = s_["starts_at_local"][11:16]
        avail_ids = set(s_["available_table_ids"])
        for tid_ in tables:
            sel = t(cell_tid(tid_, hhmm))
            if page.locator(sel).count() != 1:
                miss.append(cell_tid(tid_, hhmm)); continue
            dv = page.locator(sel).get_attribute("data-available")
            want = "true" if tid_ in avail_ids else "false"
            if dv != want:
                mism.append((cell_tid(tid_, hhmm), dv, want))
        for o in s_.get("available_options", []):
            if len(o.get("table_ids", [])) == 2:
                a, b_ = o["table_ids"]
                sel = t(combo_tid(a, b_, hhmm))
                if page.locator(sel).count() != 1:
                    miss.append(combo_tid(a, b_, hhmm))
                elif page.locator(sel).get_attribute("data-available") != "true":
                    mism.append((combo_tid(a, b_, hhmm), "not-true", "true"))
    expect("U-GRID-2", not miss, f"missing cells {miss[:6]} ({len(miss)})")
    expect("U-GRID-3", not mism, f"data-available mismatches {mism[:6]}")
    # one cell per table per slot
    n_cells = page.locator(f'{t("availability-grid")} [data-available]').count()
    expect("U-GRID-4", n_cells == len(slots) * len(tables) +
           sum(1 for s_ in slots for o in s_.get("available_options", [])
               if len(o.get("table_ids", [])) == 2),
           f"cell count {n_cells}")
    # closed day -> no-slots INSTEAD of grid (r_closed opens wed only)
    d_closed = datetime.now(timezone.utc) + timedelta(days=5)
    while d_closed.weekday() == 2:
        d_closed += timedelta(days=1)
    ui_search(page, "r_closed", d_closed.strftime("%Y-%m-%d"), 2)
    ok = visible(page, "no-slots")
    grid_gone = not visible(page, "availability-grid", 800)
    expect("U-GRID-5", ok and grid_gone, f"no-slots={ok} grid_hidden={grid_gone}")
    shot(page, "no-slots")
    # Emulate the official harness wait: wait_for_selector(OR_SEL,
    # state=visible) polls and re-resolves each pass; it must settle on the
    # VISIBLE element, not lock onto a hidden first-DOM-match. Then confirm
    # the first DOM match at settle time is the expected visible element.
    f = or_wait_settles(page, "no-slots")
    expect("U-GRID-6a", f and f["vis"],
           f"closed-day: OR-selector wait settles on visible no-slots {f}")
    # open day again: the wait must settle on the visible grid
    ui_search(page, "r_ui", d0, 2)
    f = or_wait_settles(page, "availability-grid")
    expect("U-GRID-6b", f and f["vis"],
           f"open-day: OR-selector wait settles on visible grid {f}")
    return d0

def sec_signed_out_click(page, d0):
    """Fresh browser context, no session: click an available cell."""
    ctx = page.context.browser.new_context()
    pg = ctx.new_page()
    ui_search(pg, "r_ui", d0, 2)
    pg.wait_for_selector(t(cell_tid("t_gar", "14:00")), timeout=TMO_MS)
    pg.click(t(cell_tid("t_gar", "14:00")))
    time.sleep(0.4)
    auth_err = pg.locator(t("auth-error")).count() > 0 and \
        pg.locator(t("auth-error")).is_visible()
    on_login = pg.url.rstrip("/").endswith("/login")
    no_form = not visible(pg, "booking-form", 800)
    expect("U-CELL-1", (auth_err or on_login) and no_form,
           f"signed-out click: auth_error={auth_err} login_nav={on_login} form={not no_form}")
    pg.close(); ctx.close()

def sec_unavailable_click(page, d0):
    ui_search(page, "r_ui", d0, 9)   # party 9: nothing fits any single
    sel = t(cell_tid("t_win", "14:00"))
    page.wait_for_selector(sel, timeout=TMO_MS)
    expect("U-CELL-2", page.locator(sel).get_attribute("data-available") == "false",
           "oversized party renders unavailable cells")
    page.click(sel)
    time.sleep(0.3)
    expect("U-CELL-3", not visible(page, "booking-form", 800),
           "unavailable cell does nothing")

def demo_res_count():
    st, hd, b = call("POST", "/auth/login",
                     body={"email": "demo@example.com", "password": "password-demo-9"})
    tok = (j(b) or {}).get("token")
    st, hd, b = call("GET", "/reservations", token=tok)
    return (j(b) or {}).get("reservations", []), tok

def sec_booking(page, d0):
    ui_search(page, "r_ui", d0, 2)
    page.wait_for_selector(t(cell_tid("t_gar", "14:00")), timeout=TMO_MS)
    page.click(t(cell_tid("t_gar", "14:00")))
    expect("U-BK-1", visible(page, "booking-form"), "form opens on available cell")
    summ = page.text_content(t("booking-summary")) or ""
    expect("U-BK-2", "Garden Table" in summ and "14:00" in summ,
           f"summary {summ!r}")
    pv = page.locator(t("booking-party-size")).input_value()
    expect("U-BK-3", pv == "2", f"party pre-filled {pv!r}")
    shot(page, "booking-form")
    page.click(t("booking-submit"))
    ok = visible(page, "confirmation")
    expect("U-BK-4", ok, "confirmation shown")
    ref_txt = (page.text_content(t("confirmation-reference")) or "").strip()
    expect("U-BK-5", re.fullmatch(r"[A-Z0-9]{6,12}", ref_txt or "") is not None,
           f"reference exact text {ref_txt!r}")
    det = page.text_content(t("confirmation-details")) or ""
    expect("U-BK-6", "Zum Anker" in det and "Garden Table" in det and "14:00" in det,
           f"details {det!r}")
    expect("U-BK-7", has(page, "booking-form"), "form stays after success")
    shot(page, "confirmation")
    # unchanged resubmit -> same reference, no error, no second booking
    page.click(t("booking-submit"))
    time.sleep(0.6)
    ref2 = (page.text_content(t("confirmation-reference")) or "").strip()
    res, _ = demo_res_count()
    n_slot = sum(1 for r in res if r.get("starts_at_local") == f"{d0}T14:00")
    expect("U-BK-8", ref2 == ref_txt and n_slot == 1
           and not visible(page, "booking-error", 800),
           f"resubmit ref={ref2!r} count={n_slot}")
    # field change -> NEW request -> 409 against own booking -> booking-error
    page.fill(t("booking-party-size"), "3")
    page.click(t("booking-submit"))
    expect("U-BK-9", visible(page, "booking-error"),
           "changed field = new request (409 surfaced)")
    res, _ = demo_res_count()
    expect("U-BK-9b", sum(1 for r in res if r.get("starts_at_local") == f"{d0}T14:00") == 1,
           "no duplicate created")
    shot(page, "booking-error-409")
    return ref_txt

def sec_thief(page, d0, thief_tok):
    ui_search(page, "r_ui", d0, 2)
    sel = t(cell_tid("t_pat", "16:00"))
    page.wait_for_selector(sel, timeout=TMO_MS)
    page.click(sel)
    expect("U-THF-1", visible(page, "booking-form"), "form open pre-theft")
    page.fill(t("booking-party-size"), "4")
    # thief takes the table between open and submit
    st, hd, b = call("POST", "/reservations", token=thief_tok, idem="thief-1",
        body={"restaurant_id": "r_ui", "table_id": "t_pat",
              "starts_at_local": f"{d0}T16:00", "party_size": 2})
    expect("U-THF-2", st == 201, f"thief booked st={st}")
    page.click(t("booking-submit"))
    ok = visible(page, "booking-error")
    expect("U-THF-3", ok, "booking-error on 409")
    expect("U-THF-4", not visible(page, "confirmation", 800),
           "no confirmation for the failed attempt")
    pv = page.locator(t("booking-party-size")).input_value()
    expect("U-THF-5", pv == "4" and has(page, "booking-form"),
           f"form+inputs preserved pv={pv!r}")
    # availability refreshed: that cell now unavailable
    try:
        page.wait_for_function(
            f"document.querySelector('{t(cell_tid('t_pat','16:00'))}')"
            "?.getAttribute('data-available') === 'false'", timeout=TMO_MS)
        refreshed = True
    except Exception:
        refreshed = False
    expect("U-THF-6", refreshed, "availability refreshed after 409")
    shot(page, "booking-error-thief")

def sec_dropped(page, d0):
    ui_search(page, "r_ui", d0, 2)
    sel = t(cell_tid("t_win", "18:00"))
    page.wait_for_selector(sel, timeout=TMO_MS)
    page.click(sel)
    page.wait_for_selector(t("booking-form"), timeout=TMO_MS)
    # drop the response AFTER the server commits (fetch then abort)
    state = {"fired": False}
    def drop(route):
        if route.request.method == "POST" and not state["fired"]:
            state["fired"] = True
            try:
                route.fetch()
            except Exception:
                pass
            route.abort()
        else:
            route.continue_()
    page.route(re.compile(r".*/reservations$"), drop)
    page.click(t("booking-submit"))
    ok = visible(page, "booking-uncertain")
    expect("U-DRP-1", ok, "nonempty booking-uncertain on lost response")
    txt = (page.text_content(t("booking-uncertain")) or "").strip()
    expect("U-DRP-1b", bool(txt), f"uncertain text {txt!r}")
    expect("U-DRP-2", not visible(page, "booking-error", 800)
           and not visible(page, "confirmation", 800),
           "no error/confirmation for uncertain attempt")
    shot(page, "booking-uncertain")
    page.unroute(re.compile(r".*/reservations$"))
    page.click(t("booking-submit"))
    ok = visible(page, "confirmation")
    ref_txt = (page.text_content(t("confirmation-reference")) or "").strip()
    res, _ = demo_res_count()
    mine = [r for r in res if r.get("starts_at_local") == f"{d0}T18:00"]
    expect("U-DRP-3", ok and mine and mine[0].get("reference") == ref_txt,
           f"retry recovered original ref {ref_txt!r}")
    expect("U-DRP-4", len(mine) == 1, f"exactly one booking n={len(mine)}")
    expect("U-DRP-5", not visible(page, "booking-uncertain", 800)
           and not visible(page, "booking-error", 800),
           "uncertainty cleared after successful retry")

def sec_out_of_order(page, d0):
    """Search A starts first, finishes last; grid must still describe B."""
    d1 = (datetime.now(timezone.utc) + timedelta(days=6)).strftime("%Y-%m-%d")
    held = []
    def hold_a(route):
        if "r_closed" in route.request.url:
            try:
                resp = route.fetch()
                held.append((route, resp))
                return
            except Exception:
                pass
        route.continue_()
    page.route(re.compile(r".*/availability.*"), hold_a)
    ui_search(page, "r_closed", d1, 2)      # A: closed restaurant -> no slots
    time.sleep(0.5)                          # A's response arrived, held
    page.select_option(t("restaurant-select"), "r_ui")
    page.fill(t("date-input"), d1)
    page.click(t("search-button"))           # B: open restaurant -> grid
    ok = visible(page, "availability-grid")
    expect("U-OOO-1", ok, "B results rendered")
    for route, resp in held:                 # A lands late
        try:
            route.fulfill(response=resp)
        except Exception:
            route.continue_()
    time.sleep(0.6)
    still_b = page.locator(t(cell_tid("t_win", "14:00"))).count() == 1 and \
        not visible(page, "no-slots", 800)
    expect("U-OOO-2", still_b, "late A response must not restore A's results")
    page.unroute(re.compile(r".*/availability.*"))

LABELS = {"t_win": "Window Nook", "t_gar": "Garden Table", "t_pat": "Patio Set"}

def sec_combo_ui(page, d0):
    ui_search(page, "r_ui", d0, 6)          # only pairs can fit 6
    # ask the API which pair option is actually offered (members may be taken)
    target = None
    for s_ in api_slots("r_ui", d0, 6):
        for o in s_.get("available_options", []):
            if len(o.get("table_ids", [])) == 2:
                target = (o["table_ids"], s_["starts_at_local"][11:16])
                break
        if target: break
    expect("U-CMB-0", target is not None, "api offers a pair option at p6")
    if target is None:
        return ""
    ids, hhmm = target
    ca = t(combo_tid(ids[0], ids[1], hhmm))
    ok = page.locator(ca).count() == 1
    expect("U-CMB-1", ok, f"combo cell {combo_tid(ids[0], ids[1], hhmm)}")
    if ok:
        expect("U-CMB-2",
               page.locator(ca).get_attribute("data-available") == "true",
               "combo cell carries data-available")
    page.click(ca)
    summ = page.text_content(t("booking-summary")) or ""
    lab_a, lab_b = LABELS[ids[0]], LABELS[ids[1]]
    expect("U-CMB-3", lab_a in summ and lab_b in summ,
           f"summary names every table {summ!r}")
    page.click(t("booking-submit"))
    ok = visible(page, "confirmation")
    expect("U-CMB-4", ok, "combo confirmation")
    cts = page.text_content(t("confirmation-tables")) or ""
    expect("U-CMB-5", lab_a in cts and lab_b in cts,
           f"confirmation-tables {cts!r}")
    ref_txt = (page.text_content(t("confirmation-reference")) or "").strip()
    res, _ = demo_res_count()
    mine = [r for r in res if r.get("reference") == ref_txt]
    expect("U-CMB-6", mine and mine[0].get("table_ids") == list(ids),
           f"server stored canonical pair {mine and mine[0].get('table_ids')}")
    shot(page, "combo-confirmation")
    return ref_txt

def sec_lookup(page, combo_ref):
    page.goto(BASE + "/lookup")
    page.fill(t("lookup-reference-input"), "ZZZ999")
    page.click(t("lookup-submit"))
    expect("U-LKP-1", visible(page, "reservation-error"),
           "reservation-error on not-found")
    page.fill(t("lookup-reference-input"), combo_ref)
    page.click(t("lookup-submit"))
    ok = visible(page, "reservation-detail")
    expect("U-LKP-2", ok, "reservation-detail on found")
    stat = (page.text_content(t("reservation-status")) or "").strip()
    expect("U-LKP-3", stat == "confirmed", f"status text exact {stat!r}")
    rt = page.text_content(t("reservation-tables")) or ""
    res, _ = demo_res_count()
    booked = next((r for r in res if r.get("reference") == combo_ref), {})
    want_labs = [LABELS[x] for x in (booked.get("table_ids") or [])]
    expect("U-LKP-4", bool(want_labs) and all(w in rt for w in want_labs),
           f"reservation-tables {rt!r} want {want_labs}")
    page.click(t("reservation-cancel-button"))
    stat2 = ""
    try:
        page.wait_for_function(
            "document.querySelector('[data-testid=\"reservation-status\"]')"
            "?.textContent.trim() === 'cancelled'", timeout=TMO_MS)
        stat2 = (page.text_content(t("reservation-status")) or "").strip()
    except Exception:
        pass
    expect("U-LKP-5", stat2 == "cancelled", f"status after cancel {stat2!r}")
    gone = page.locator(t("reservation-cancel-button")).count() == 0 or \
        not page.locator(t("reservation-cancel-button")).is_visible()
    expect("U-LKP-6", gone, "cancel button absent once cancelled")
    # refused cancel (inside cutoff) -> reservation-error
    page.fill(t("lookup-reference-input"), "NEAR01")
    page.click(t("lookup-submit"))
    page.wait_for_selector(t("reservation-detail"), timeout=TMO_MS)
    page.click(t("reservation-cancel-button"))
    expect("U-LKP-7", visible(page, "reservation-error"),
           "reservation-error on refused cancel")
    shot(page, "lookup")

def sec_viewport(browser, d0):
    ctx = browser.new_context(viewport={"width": 375, "height": 800})
    pg = ctx.new_page()
    def no_hscroll(tag):
        sw = pg.evaluate("document.documentElement.scrollWidth")
        iw = pg.evaluate("window.innerWidth")
        expect(f"U-VP:{tag}", sw <= iw + 1, f"scrollWidth={sw} inner={iw}")
    pg.goto(BASE + "/login"); no_hscroll("login")
    pg.fill(t("login-email"), "demo@example.com")
    pg.fill(t("login-password"), "password-demo-9")
    pg.click(t("login-submit"))
    pg.wait_for_selector(t("current-user"), timeout=TMO_MS)
    pg.goto(BASE + "/"); no_hscroll("home")
    pg.select_option(t("restaurant-select"), "r_ui")
    pg.fill(t("date-input"), d0)
    pg.fill(t("party-size-input"), "2")
    pg.click(t("search-button"))
    pg.wait_for_selector(t("availability-grid"), timeout=TMO_MS)
    no_hscroll("grid")
    pg.click(t(cell_tid("t_pat", "10:00")))
    pg.wait_for_selector(t("booking-form"), timeout=TMO_MS)
    no_hscroll("form")
    shot(pg, "viewport-375")
    pg.close(); ctx.close()

def sec_upgrade_mid_session(page, d0):
    """Import completes between browser requests: session + pending retry survive."""
    ui_search(page, "r_ui", d0, 2)
    sel = t(cell_tid("t_win", "20:00"))
    page.wait_for_selector(sel, timeout=TMO_MS)
    page.click(sel)
    page.wait_for_selector(t("booking-form"), timeout=TMO_MS)
    # lose the response (server commits), then upgrade lands, then retry
    state = {"fired": False}
    def drop(route):
        if route.request.method == "POST" and not state["fired"]:
            state["fired"] = True
            try:
                route.fetch()
            except Exception:
                pass
            route.abort()
        else:
            route.continue_()
    page.route(re.compile(r".*/reservations$"), drop)
    page.click(t("booking-submit"))
    visible(page, "booking-uncertain")
    # the upgrade: export then import between browser requests
    st, hd, b = call("GET", "/_test/export")
    st2, hd2, b2 = call("POST", "/_test/import", raw=b)
    expect("U-UPG-1", st == 200 and st2 == 204, f"export/import {st}/{st2}")
    # still signed in without reload
    cu = page.locator(t("current-user")).count() > 0 and \
        "Demo Diner" in (page.text_content(t("current-user")) or "")
    expect("U-UPG-2", cu, "current-user survives import between requests")
    page.unroute(re.compile(r".*/reservations$"))
    page.click(t("booking-submit"))
    ok = visible(page, "confirmation")
    ref_txt = (page.text_content(t("confirmation-reference")) or "").strip()
    res, _ = demo_res_count()
    mine = [r for r in res if r.get("starts_at_local") == f"{d0}T20:00"]
    expect("U-UPG-3", ok and mine and mine[0].get("reference") == ref_txt,
           "pending retry identity survived; original confirmation recovered")
    shot(page, "upgrade-retry")

def main():
    global BASE, SHOTS
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--shots", default=None,
                    help="screenshot dir (default <repo>/evidence/raw/ui-s2)")
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")
    repo = pathlib.Path(__file__).resolve().parents[2]
    SHOTS = pathlib.Path(args.shots) if args.shots else repo / "evidence" / "raw" / "ui-s2"
    SHOTS.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    near = local30(45)   # inside the 120-min cutoff, on-grid
    st, hd, b = call("POST", "/_test/reset", body=fixture_ui(near))
    if st != 204:
        expect("U-SETUP", False, f"reset st={st} body={b[:200]!r}")
        print("== aborting: reset failed =="); sys.exit(1)
    st, hd, b = call("POST", "/auth/login",
                     body={"email": "thief@example.com", "password": "password-thief-9"})
    thief_tok = (j(b) or {}).get("token")
    t0 = time.monotonic()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()
            page.set_default_timeout(TMO_MS)
            try:
                sec_routes(page)
                sec_testids(page)
                sec_auth(page)
                d0 = sec_grid(page, None)
                sec_signed_out_click(page, d0)
                sec_unavailable_click(page, d0)
                sec_booking(page, d0)
                sec_thief(page, d0, thief_tok)
                sec_dropped(page, d0)
                sec_out_of_order(page, d0)
                cref = sec_combo_ui(page, d0)
                sec_lookup(page, cref)
                sec_upgrade_mid_session(page, d0)
                sec_viewport(browser, d0)
            except Exception as e:
                expect("U-EXC", False, f"check raised {e!r}")
                try:
                    shot(page, "exception-state")
                except Exception:
                    pass
            ctx.close(); browser.close()
    except Exception as e:
        expect("U-INIT", False, f"playwright init failed {e!r}")
    fails = [c for c, ok in RESULTS if not ok]
    print(f"\n== {len(RESULTS)} UI checks, {len(fails)} FAIL, "
          f"{time.monotonic()-t0:.1f}s ==")
    for c in fails:
        print("FAIL", c)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
