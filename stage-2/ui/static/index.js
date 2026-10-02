/* Tablekeeper — / : search, availability grid, booking flow.

   Behaviour contract (stage-2 spec + matrix U2/U5/U6/U7/C5):
   - A search generation counter makes a late older response unable to
     repaint over a newer one.
   - Cells: slot-{table_id}-{HH:MM} for every table × slot, and
     slot-{a}+{b}-{HH:MM} for each declared pair that is available for
     the searched party size (R2-5: rendered only when available).
   - data-available is "true" iff the table is in the slot's
     available_table_ids (singles) / the pair is in available_options.
   - The booking form mints its Idempotency-Key when it opens; a changed
     field mints a new key; an unchanged resubmit replays.
   - A lost response (network/timeout, incl. after commit) shows
     booking-uncertain and keeps the same key+body for retry. A refused
     response shows booking-error. The server is authoritative. */
(function () {
  "use strict";

  var el = TK.el;
  var api = TK.api;

  var searchForm = document.getElementById("search-form");
  var restaurantSelect = document.getElementById("restaurant-select");
  var dateInput = document.getElementById("date-input");
  var partyInput = document.getElementById("party-size-input");
  var searchStatus = document.getElementById("search-status");
  var authNudge = document.getElementById("auth-nudge");
  var resultsEmpty = document.getElementById("results-empty");
  var loadingSlot = document.getElementById("loading-slot");
  var noSlots = document.querySelector('[data-testid="no-slots"]');
  var noSlotsParent = noSlots.parentNode;
  var noSlotsNext = noSlots.nextSibling;
  var gridScroll = document.getElementById("grid-scroll");
  var gridEl = document.getElementById("availability-grid");
  var bookingSlot = document.getElementById("booking-slot");
  var confirmationSlot = document.getElementById("confirmation-slot");

  var searchGen = 0;              // only the newest search may paint
  var lastSearch = null;          // {rid, date, party}
  var restCache = {};             // rid -> restaurant detail
  var selection = null;           // {tableIds:[...], local:"YYYY-MM-DDTHH:MM"}
  var pending = null;             // {key, bodyJson} — retry identity

  /* ---- bootstrap ---------------------------------------------------- */

  function todayISO() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

  function loadRestaurants() {
    api("/restaurants").then(function (res) {
      if (!res.ok || !res.body || !res.body.restaurants) {
        searchStatus.textContent =
          "We could not load the restaurant list. Please retry.";
        return;
      }
      restaurantSelect.innerHTML = "";
      res.body.restaurants.forEach(function (r) {
        restaurantSelect.appendChild(
          el("option", { value: r.id }, r.name));
      });
      if (res.body.restaurants.length) {
        restaurantSelect.value = res.body.restaurants[0].id;
      }
    }).catch(function () {
      searchStatus.textContent =
        "We could not load the restaurant list. Please retry.";
    });
  }

  function restaurantDetail(rid) {
    if (restCache[rid]) return Promise.resolve(restCache[rid]);
    return api("/restaurants/" + encodeURIComponent(rid)).then(function (res) {
      if (!res.ok || !res.body) throw new Error("restaurant fetch failed");
      restCache[rid] = res.body;
      return res.body;
    });
  }

  dateInput.value = todayISO();
  loadRestaurants();

  /* ---- helpers ------------------------------------------------------- */

  function labelOf(rest, tid) {
    var t = (rest.tables || []).find(function (x) { return x.id === tid; });
    return (t && t.label) ? t.label : tid;
  }

  function capacityOf(rest, tid) {
    var t = (rest.tables || []).find(function (x) { return x.id === tid; });
    return t ? t.capacity : 0;
  }

  function joinLabels(rest, tableIds) {
    return tableIds.map(function (t) { return labelOf(rest, t); })
      .join(" + ");
  }

  function showAuthNudge() {
    authNudge.innerHTML = "";
    var box = el("p", {
      "data-testid": "auth-error",
      className: "inline-msg msg-info",
      role: "alert",
    });
    box.appendChild(document.createTextNode(
      "Please sign in to book a table. "));
    var link = el("a", { href: "/login" }, "Log in");
    box.appendChild(link);
    box.appendChild(document.createTextNode(" or "));
    box.appendChild(el("a", { href: "/signup" }, "create an account"));
    box.appendChild(document.createTextNode("."));
    authNudge.appendChild(box);
  }

  function clearAuthNudge() { authNudge.innerHTML = ""; }

  /* ---- search -------------------------------------------------------- */

  function setLoading(on) {
    loadingSlot.innerHTML = "";
    if (on) {
      var line = el("div", { className: "loading-line", role: "status" });
      line.appendChild(el("span", { className: "spinner", "aria-hidden": "true" }));
      line.appendChild(document.createTextNode("Checking the dining room…"));
      loadingSlot.appendChild(line);
    }
  }

  function runSearch(userInitiated) {
    var rid = restaurantSelect.value;
    var date = dateInput.value;
    var party = parseInt(partyInput.value, 10);
    if (!rid || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !(party >= 1)) {
      searchStatus.textContent =
        "Pick a restaurant, a date and a party size of at least 1.";
      return;
    }

    var gen = ++searchGen;
    var params = { rid: rid, date: date, party: party };
    setLoading(true);
    searchStatus.textContent = "";

    var detailP = restaurantDetail(rid);
    var availP = api("/availability?restaurant_id=" +
      encodeURIComponent(rid) + "&date=" + encodeURIComponent(date) +
      "&party_size=" + encodeURIComponent(String(party)));

    Promise.all([detailP, availP]).then(function (pair) {
      if (gen !== searchGen) return;   // a newer search owns the screen
      setLoading(false);
      var rest = pair[0];
      var res = pair[1];
      if (!res.ok || !res.body || !Array.isArray(res.body.slots)) {
        searchStatus.textContent =
          TK.errorMessage(res, "Availability is unavailable right now.");
        return;
      }
      lastSearch = params;
      if (userInitiated) {
        closeBooking();
        clearConfirmation();
        clearAuthNudge();
      }
      renderGrid(rest, res.body, params);
    }).catch(function () {
      if (gen !== searchGen) return;
      setLoading(false);
      searchStatus.textContent =
        "We could not reach the service. Your search was not placed — " +
        "please try again.";
    });
  }

  searchForm.addEventListener("submit", function (e) {
    e.preventDefault();
    runSearch(true);
  });

  /* ---- grid ----------------------------------------------------------- */

  /* S2-1: after a completed search the inapplicable element leaves the DOM
     entirely, so a client waiting on the OR-selector
     "availability-grid, no-slots" can only resolve the visible node —
     DOM order can no longer hand it a hidden match. */
  function showGrid() {
    if (noSlots.parentNode) noSlots.parentNode.removeChild(noSlots);
    if (gridEl.parentNode !== gridScroll) gridScroll.appendChild(gridEl);
    gridScroll.hidden = false;
  }

  function showNoSlots() {
    gridEl.innerHTML = "";   // stale cells stop matching too
    if (gridEl.parentNode) gridEl.parentNode.removeChild(gridEl);
    gridScroll.hidden = true;
    if (!noSlots.parentNode) {
      noSlotsParent.insertBefore(noSlots, noSlotsNext);
    }
    noSlots.hidden = false;
  }

  function renderGrid(rest, data, params) {
    resultsEmpty.hidden = true;
    gridEl.innerHTML = "";

    var sub = document.getElementById("results-sub");
    sub.textContent = rest.name + " — " + TK.fmtDate(data.date) +
      " · party of " + params.party + " (" + data.timezone + ")";

    if (!data.slots.length) {
      showNoSlots();
      return;
    }
    showGrid();

    var pairs = rest.combinable || [];
    var pairKey = function (ids) { return ids.slice().sort().join("+"); };

    var thead = el("thead");
    var hrow = el("tr");
    hrow.appendChild(el("th", { scope: "col" }, "Time"));
    (rest.tables || []).forEach(function (t) {
      var th = el("th", { scope: "col" });
      th.appendChild(document.createTextNode(t.label || t.id));
      th.appendChild(el("span", { className: "pair-of" },
        "seats " + t.capacity));
      hrow.appendChild(th);
    });
    pairs.forEach(function (p) {
      var th = el("th", { scope: "col", className: "pair-head" });
      th.appendChild(document.createTextNode(joinLabels(rest, p)));
      var cap = p.reduce(function (n, t) {
        return n + capacityOf(rest, t);
      }, 0);
      th.appendChild(el("span", { className: "pair-of" },
        "combined · seats " + cap));
      hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    gridEl.appendChild(thead);

    var tbody = el("tbody");
    data.slots.forEach(function (slot) {
      var hhmm = TK.hhmm(slot.starts_at_local);
      var tr = el("tr");
      tr.appendChild(el("td", { className: "time-col" }, hhmm));

      var free = {};
      (slot.available_table_ids || []).forEach(function (t) { free[t] = true; });
      var availPairs = {};
      (slot.available_options || []).forEach(function (o) {
        if (o.table_ids.length === 2) availPairs[pairKey(o.table_ids)] = o;
      });

      (rest.tables || []).forEach(function (t) {
        var td = el("td", {
          "data-testid": "slot-" + t.id + "-" + hhmm,
          "data-available": free[t.id] ? "true" : "false",
          "data-tables": JSON.stringify([t.id]),
          "data-local": slot.starts_at_local,
        });
        if (free[t.id]) {
          td.appendChild(el("button", {
            className: "slot", type: "button",
          }, "Available"));
        } else {
          td.appendChild(el("div", {
            className: "slot " +
              (t.capacity < params.party ? "slot-small" : "slot-taken"),
          }, t.capacity < params.party
            ? "Seats " + t.capacity : "Taken"));
        }
        tr.appendChild(td);
      });

      pairs.forEach(function (p) {
        var opt = availPairs[pairKey(p)];
        if (!opt) {
          // R2-5: combination cells exist only when the pair is offered
          tr.appendChild(el("td", { className: "slot-pair" }));
          return;
        }
        var td = el("td", {
          "data-testid": "slot-" + p[0] + "+" + p[1] + "-" + hhmm,
          "data-available": "true",
          "data-tables": JSON.stringify(opt.table_ids),
          "data-local": slot.starts_at_local,
          className: "slot-pair",
        });
        var btn = el("button", { className: "slot", type: "button" },
          "Together");
        btn.appendChild(el("span", { className: "cap" },
          "seats " + opt.capacity));
        td.appendChild(btn);
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
    gridEl.appendChild(tbody);
  }

  gridEl.addEventListener("click", function (e) {
    var cell = e.target.closest("[data-available]");
    if (!cell || cell.getAttribute("data-available") !== "true") return;
    var tableIds;
    try { tableIds = JSON.parse(cell.getAttribute("data-tables")); }
    catch (err) { return; }
    var local = cell.getAttribute("data-local");

    if (!TK.token()) {           // U5-6 / R2-15: signed-out → auth-error
      showAuthNudge();
      return;
    }
    clearAuthNudge();
    openBooking(tableIds, local, cell);
  });

  /* ---- booking form --------------------------------------------------- */

  function bookingBody(party) {
    var body = {
      restaurant_id: lastSearch.rid,
      starts_at_local: selection.local,
      party_size: party,
    };
    if (selection.tableIds.length === 1) {
      body.table_id = selection.tableIds[0];
    } else {
      body.table_ids = selection.tableIds.slice();
    }
    return body;
  }

  function openBooking(tableIds, local, cellEl) {
    var rest = restCache[lastSearch.rid];
    var prev = gridEl.querySelector(".slot-picked");
    if (prev) prev.classList.remove("slot-picked");
    var inner = cellEl.querySelector(".slot") || cellEl;
    inner.classList.add("slot-picked");

    selection = { tableIds: tableIds.slice(), local: local };
    pending = { key: TK.newIdempotencyKey(), bodyJson: null };
    clearConfirmation();

    bookingSlot.innerHTML = "";
    var card = el("section", {
      className: "card booking-card",
      "data-testid": "booking-form",
      "aria-labelledby": "booking-h",
    });
    card.appendChild(el("h2", { id: "booking-h" },
      tableIds.length === 1 ? "Reserve this table" : "Reserve these tables"));

    var summary = el("p", {
      "data-testid": "booking-summary",
      className: "booking-summary",
    });
    summary.appendChild(el("strong", null,
      tableIds.length === 1
        ? "Table " + joinLabels(rest, tableIds)
        : "Tables " + joinLabels(rest, tableIds)));
    summary.appendChild(document.createTextNode(
      " — " + TK.fmtLocal(local)));
    card.appendChild(summary);

    var form = el("form", { id: "booking-form-el" });
    var row = el("div", { className: "booking-row" });
    var field = el("div", { className: "field" });
    field.appendChild(el("label", { "for": "booking-party-size" },
      "Party size"));
    var cap = tableIds.reduce(function (n, t) {
      return n + capacityOf(rest, t);
    }, 0);
    var pinput = el("input", {
      id: "booking-party-size",
      "data-testid": "booking-party-size",
      type: "number", min: "1", max: String(cap), step: "1",
      value: String(lastSearch.party),
      required: "required",
    });
    field.appendChild(pinput);
    row.appendChild(field);
    row.appendChild(el("button", {
      className: "btn btn-primary",
      "data-testid": "booking-submit",
      type: "submit",
    }, "Confirm booking"));
    form.appendChild(row);
    form.appendChild(el("div", {
      className: "booking-notes", id: "booking-notes",
    }));
    card.appendChild(form);
    bookingSlot.appendChild(card);

    form.addEventListener("submit", submitBooking);
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function closeBooking() {
    bookingSlot.innerHTML = "";
    selection = null;
    pending = null;
    var prev = gridEl.querySelector(".slot-picked");
    if (prev) prev.classList.remove("slot-picked");
  }

  function note(kind, text) {
    // booking-error and booking-uncertain exist only while their state
    // does — attach/detach, never hidden leftovers.
    var host = document.getElementById("booking-notes");
    if (!host) return;
    host.querySelectorAll('[data-testid="booking-error"],' +
      '[data-testid="booking-uncertain"]').forEach(function (n) {
      n.remove();
    });
    if (!kind) return;
    host.appendChild(el("p", {
      "data-testid": kind === "error"
        ? "booking-error" : "booking-uncertain",
      className: "inline-msg " + (kind === "error" ? "msg-error" : "msg-warn"),
      role: "alert",
    }, text));
  }

  function clearConfirmation() { confirmationSlot.innerHTML = ""; }

  function showConfirmation(body) {
    var rest = restCache[body.restaurant_id] || restCache[lastSearch.rid];
    var ids = body.table_ids || (body.table_id ? [body.table_id] : []);
    var names = ids.map(function (t) { return labelOf(rest, t); });

    confirmationSlot.innerHTML = "";
    var card = el("section", {
      className: "confirmation-card",
      "data-testid": "confirmation",
      "aria-labelledby": "conf-h",
    });
    card.appendChild(el("p", { className: "confirmation-kicker" },
      "Booking confirmed"));
    var refLine = el("p", { className: "confirmation-ref" });
    refLine.appendChild(el("span", {
      "data-testid": "confirmation-reference",
    }, body.reference));
    card.appendChild(refLine);

    var details = el("p", {
      "data-testid": "confirmation-details",
      className: "confirmation-details",
    }, rest.name + " · " + names.join(" + ") + " · " +
      TK.fmtLocal(body.starts_at_local));
    card.appendChild(details);

    card.appendChild(el("p", {
      "data-testid": "confirmation-tables",
      className: "confirmation-tables-line",
    }, names.join(" + ")));

    card.appendChild(el("a", {
      className: "btn btn-ghost btn-sm",
      href: "/lookup?ref=" + encodeURIComponent(body.reference),
    }, "View or cancel this booking"));
    confirmationSlot.appendChild(card);
  }

  function submitBooking(e) {
    e.preventDefault();
    if (!selection || !pending) return;
    var rest = restCache[lastSearch.rid];
    var pinput = document.getElementById("booking-party-size");
    var submitBtn = document.querySelector('[data-testid="booking-submit"]');
    var party = parseInt(pinput.value, 10);
    if (!(party >= 1)) {
      note("error", "Enter a party size of at least 1.");
      return;
    }

    var body = bookingBody(party);
    var bodyJson = JSON.stringify(body);
    if (pending.bodyJson !== bodyJson) {
      // any changed field → a brand-new booking request (new key)
      pending = { key: TK.newIdempotencyKey(), bodyJson: bodyJson };
    }

    submitBtn.disabled = true;
    clearConfirmation();          // no stale confirmation while in flight
    note(null);

    api("/reservations", {
      method: "POST", body: body,
      token: TK.token(), key: pending.key,
    }).then(function (res) {
      submitBtn.disabled = false;
      if (res.ok && res.body && res.body.reference) {
        // 201 first use or 200 replay — the reference is the original
        pending.bodyJson = bodyJson;
        note(null);
        showConfirmation(res.body);
        return;
      }
      var code = res.body && res.body.error && res.body.error.code;
      note("error", TK.errorMessage(res, "That booking was refused."));
      if (res.status === 409 && code === "table_unavailable") {
        // someone else took it after the form opened: keep the form and
        // its inputs, refresh availability so the grid is truthful
        runSearch(false);
      }
    }).catch(function () {
      // Lost response — possibly after commit server-side. Same key and
      // body retry below; no error, no fabricated confirmation.
      submitBtn.disabled = false;
      note("uncertain",
        "We could not confirm whether this booking went through. " +
        "Press Confirm booking again to retry — it is safe to retry.");
    });
  }
})();
