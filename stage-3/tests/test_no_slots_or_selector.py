#!/usr/bin/env python3
"""S2-1 regression check (tk-experience): after every completed search the
first DOM-order match among [data-testid=no-slots] and
[data-testid=availability-grid] must be the VISIBLE one — the inapplicable
element leaves the DOM.

Reproduces the original failure: an OR-selector state="visible" wait hung
because the hidden no-slots node preceded the grid in DOM order.

Run:
  D:\\tk-official\\.venv\\Scripts\\python.exe tests\\test_no_slots_or_selector.py \
      --base-url http://localhost:8091
"""
import argparse, json, re, sys, urllib.request, urllib.error

BASE = "http://localhost:8091"
OR_SEL = ('[data-testid="no-slots"], [data-testid="availability-grid"]')
RESULTS = []

def expect(cid, ok, detail=""):
    RESULTS.append((cid, bool(ok)))
    print(("PASS" if ok else "FAIL"), cid, "-", detail, flush=True)

def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(BASE + path, data=data, headers=h,
                               method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    args = ap.parse_args()
    BASE = args.base_url.rstrip("/")

    # r_open serves every day; r_shut has no opening_hours at all.
    fixture = {
        "users": [],
        "restaurants": [
            {"id": "r_open", "name": "Open House", "timezone": "UTC",
             "slot_minutes": 30, "reservation_duration_minutes": 90,
             "cancellation_cutoff_minutes": 60,
             "opening_hours": [{"weekday": w, "opens": "10:00",
                                "closes": "22:00"}
                               for w in ("mon", "tue", "wed", "thu", "fri",
                                         "sat", "sun")],
             "tables": [{"id": "t_a", "label": "A", "capacity": 4}]},
            {"id": "r_shut", "name": "Shut Inn", "timezone": "UTC",
             "slot_minutes": 30, "reservation_duration_minutes": 90,
             "cancellation_cutoff_minutes": 60,
             "opening_hours": [],
             "tables": [{"id": "t_b", "label": "B", "capacity": 4}]},
        ],
        "reservations": [],
    }
    st, body = call("POST", "/_test/reset", body=fixture)
    if st != 204:
        print("reset failed", st, body[:200]); sys.exit(1)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        page = pw.chromium.launch().new_page()
        page.set_default_timeout(6000)
        page.goto(BASE + "/")
        page.wait_for_selector(
            '[data-testid="restaurant-select"] option', state="attached")
        page.fill('[data-testid="date-input"]', "2026-10-08")
        page.fill('[data-testid="party-size-input"]', "2")

        def search(rid):
            page.select_option('[data-testid="restaurant-select"]', rid)
            page.click('[data-testid="search-button"]')

        def first_or_testid():
            el = page.wait_for_selector(OR_SEL, state="visible",
                                        timeout=5000)
            return el.get_attribute("data-testid")

        def counts():
            return (page.locator('[data-testid="no-slots"]').count(),
                    page.locator('[data-testid="availability-grid"]')
                    .count(),
                    page.locator('[data-testid^="slot-"]').count())

        # 1. day WITH slots: OR-wait must resolve the visible GRID fast,
        #    no-slots must not even match. (Wait for the new render —
        #    slot cells appearing — before the OR probe.)
        search("r_open")
        page.wait_for_selector('[data-testid^="slot-"]', state="attached")
        got = first_or_testid()
        n_no, n_grid, n_cells = counts()
        expect("S2-1-grid-first", got == "availability-grid",
               f"OR resolved {got!r}")
        expect("S2-1-noslots-gone", n_no == 0,
               f"no-slots matches={n_no}")
        expect("S2-1-cells", n_cells > 0, f"slot cells={n_cells}")

        # 2. closed day: OR-wait must resolve the visible NO-SLOTS node;
        #    the grid (and its cells) must not match.
        search("r_shut")
        page.wait_for_selector('[data-testid="no-slots"]',
                               state="visible")
        got = first_or_testid()
        n_no, n_grid, n_cells = counts()
        expect("S2-1-noslots-first", got == "no-slots",
               f"OR resolved {got!r}")
        expect("S2-1-grid-gone", n_grid == 0, f"grid matches={n_grid}")
        expect("S2-1-cells-gone", n_cells == 0,
               f"stale slot cells={n_cells}")

        # 3. toggle back: grid re-attaches and wins again (cells were
        #    cleared while closed, so a new slot cell marks the render).
        search("r_open")
        page.wait_for_selector('[data-testid^="slot-"]', state="attached")
        got = first_or_testid()
        n_no, n_grid, n_cells = counts()
        expect("S2-1-toggle-back", got == "availability-grid"
               and n_no == 0 and n_cells > 0,
               f"OR resolved {got!r} cells={n_cells}")

        page.close()

    fails = [c for c, ok in RESULTS if not ok]
    print(f"== {len(RESULTS)} S2-1 checks, {len(fails)} FAIL ==")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
