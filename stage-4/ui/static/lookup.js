/* Tablekeeper — /lookup : find a reservation by reference, cancel it.

   reservation-error exists only while an error does. A cancelled
   reservation keeps its detail card, minus the cancel button — the DOM
   is updated in place, no reload. */
(function () {
  "use strict";

  var el = TK.el;
  var api = TK.api;

  var form = document.getElementById("lookup-form");
  var input = document.getElementById("lookup-reference-input");
  var notes = document.getElementById("lookup-notes");
  var resultSlot = document.getElementById("lookup-result");

  function showError(text) {
    notes.innerHTML = "";
    notes.appendChild(el("p", {
      "data-testid": "reservation-error",
      className: "inline-msg msg-error",
      role: "alert",
    }, text));
  }

  function clearError() { notes.innerHTML = ""; }

  function fetchLabels(body) {
    // resolve table ids to restaurant labels; degrade to ids on failure
    return api("/restaurants/" + encodeURIComponent(body.restaurant_id))
      .then(function (res) {
        if (!res.ok || !res.body) return { name: body.restaurant_id, labels: null };
        var byId = {};
        (res.body.tables || []).forEach(function (t) { byId[t.id] = t.label || t.id; });
        return { name: res.body.name, labels: byId };
      }).catch(function () {
        return { name: body.restaurant_id, labels: null };
      });
  }

  function renderDetail(body, info) {
    resultSlot.innerHTML = "";
    var ids = body.table_ids || (body.table_id ? [body.table_id] : []);
    var names = ids.map(function (t) {
      return info.labels && info.labels[t] ? info.labels[t] : t;
    });

    var card = el("article", {
      className: "card reservation-card",
      "data-testid": "reservation-detail",
    });

    card.appendChild(el("h2", null, info.name));

    var badge = el("p", { style: "margin:0 0 10px" });
    badge.appendChild(el("span", {
      "data-testid": "reservation-status",
      className: "status-badge " + (body.status === "confirmed"
        ? "is-confirmed" : "is-cancelled"),
    }, body.status));
    card.appendChild(badge);

    card.appendChild(el("p", {
      "data-testid": "reservation-tables",
      className: "reservation-tables-line",
    }, (names.length === 1 ? "Table: " : "Tables: ") + names.join(" + ")));

    card.appendChild(el("p", { className: "reservation-meta" },
      TK.fmtLocal(body.starts_at_local) + " · party of " +
      body.party_size + " · reference " + body.reference));

    resultSlot.appendChild(card);
    renderCancel(body);
  }

  function renderCancel(res) {
    var card = resultSlot.querySelector(
      '[data-testid="reservation-detail"]');
    if (!card) return;
    var old = card.querySelector('[data-testid="reservation-cancel-button"]');
    if (old) old.remove();
    if (res.status !== "confirmed") return;
    var btn = el("button", {
      "data-testid": "reservation-cancel-button",
      className: "btn btn-danger",
      type: "button",
    }, "Cancel this booking");
    card.appendChild(btn);
    btn.addEventListener("click", function () { doCancel(res.reference); });
  }

  function doCancel(ref) {
    clearError();
    api("/reservations/" + encodeURIComponent(ref) + "/cancel", {
      method: "POST", token: TK.token(),
    }).then(function (res) {
      if (res.ok && res.body) {
        fetchLabels(res.body).then(function (info) {
          renderDetail(res.body, info);
        });
        return;
      }
      showError(TK.errorMessage(res,
        "This booking could not be cancelled."));
    }).catch(function () {
      // A lost cancel response is safe to retry — a second cancel of the
      // same reference returns the current state, so just try again.
      showError("The response was lost. Press cancel again to retry.");
    });
  }

  function lookup(ref) {
    clearError();
    resultSlot.innerHTML = "";
    if (!TK.token()) {
      showError("Log in to look up a booking.");
      return;
    }
    api("/reservations/" + encodeURIComponent(ref), {
      token: TK.token(),
    }).then(function (res) {
      if (res.ok && res.body) {
        fetchLabels(res.body).then(function (info) {
          renderDetail(res.body, info);
        });
        return;
      }
      if (res.status === 404) {
        showError("No booking found under that reference.");
      } else if (res.status === 401) {
        showError("Your session is no longer valid — please log in again.");
      } else {
        showError(TK.errorMessage(res, "Lookup failed. Please try again."));
      }
    }).catch(function () {
      showError("We could not reach the service. Please try again.");
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var ref = input.value.trim();
    if (!ref) {
      showError("Enter a booking reference.");
      return;
    }
    lookup(ref);
  });

  var params = new URLSearchParams(location.search);
  if (params.get("ref")) {
    input.value = params.get("ref");
    if (TK.token()) lookup(params.get("ref"));
  }

  document.addEventListener("tk:signed-out", function () {
    resultSlot.innerHTML = "";
    showError("You have logged out. Log in to look up a booking.");
  });
})();
