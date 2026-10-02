/* Tablekeeper — shared helpers: session, header, API client, formatting. */
(function () {
  "use strict";

  var TOKEN_KEY = "tablekeeper.token";
  var NAME_KEY = "tablekeeper.display_name";

  var TK = {};

  TK.token = function () {
    try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  };

  TK.displayName = function () {
    try { return localStorage.getItem(NAME_KEY); } catch (e) { return null; }
  };

  TK.saveSession = function (token, displayName) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(NAME_KEY, displayName || "");
    } catch (e) { /* private mode: session is memory-only */ }
  };

  TK.clearSession = function () {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(NAME_KEY);
    } catch (e) { }
  };

  TK.newIdempotencyKey = function () {
    if (window.crypto && crypto.randomUUID) {
      return "ui-" + crypto.randomUUID();
    }
    return "ui-" + Date.now() + "-" + Math.random().toString(36).slice(2);
  };

  /* API call. Resolves to {status, ok, body} for any HTTP response —
     including 4xx/5xx. Rejects (throws) only when the response is lost:
     network failure, aborted request, or timeout. Callers use that
     distinction to tell a refused outcome from an uncertain one. */
  TK.api = function (path, opts) {
    opts = opts || {};
    var headers = { "Accept": "application/json" };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.token) headers["Authorization"] = "Bearer " + opts.token;
    if (opts.key) headers["Idempotency-Key"] = opts.key;

    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); },
      opts.timeoutMs || 8000);

    return fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: ctrl.signal,
    }).then(function (res) {
      return res.text().then(function (text) {
        var body = null;
        try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }
        return { status: res.status, ok: res.ok, body: body };
      });
    }).finally(function () { clearTimeout(timer); });
  };

  TK.errorMessage = function (res, fallback) {
    if (res && res.body && res.body.error && res.body.error.message) {
      return res.body.error.message;
    }
    return fallback || "Something went wrong. Please try again.";
  };

  /* ---- DOM helpers ---- */

  TK.el = function (tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "className") node.className = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  /* Human-readable "Saturday 3 October 2026 · 19:00" from a bare
     YYYY-MM-DDTHH:MM local string. Built without Date parsing so the
     restaurant's wall clock is rendered verbatim. */
  var WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday"];
  var MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];

  TK.fmtLocal = function (localStr) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(localStr || "");
    if (!m) return String(localStr || "");
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return WEEKDAYS[d.getDay()] + " " + (+m[3]) + " " + MONTHS[d.getMonth()] +
      " " + m[1] + " · " + m[4];
  };

  TK.fmtDate = function (dateStr) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || "");
    if (!m) return String(dateStr || "");
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return WEEKDAYS[d.getDay()] + " " + (+m[3]) + " " + MONTHS[d.getMonth()] +
      " " + m[1];
  };

  TK.hhmm = function (localStr) {
    var m = /T(\d{2}:\d{2})/.exec(localStr || "");
    return m ? m[1] : "";
  };

  /* Header auth area: current-user + logout-button on every screen when
     signed in; sign-in links when not. */
  TK.renderHeader = function () {
    var slot = document.getElementById("header-auth");
    if (!slot) return;
    slot.innerHTML = "";
    var name = TK.displayName();
    if (TK.token() && name !== null) {
      var who = TK.el("span", { className: "who" });
      var strong = TK.el("strong", { "data-testid": "current-user" },
        name || "Signed in");
      who.appendChild(strong);
      var out = TK.el("button", {
        "data-testid": "logout-button",
        className: "btn btn-ghost btn-sm",
        type: "button",
      }, "Log out");
      out.addEventListener("click", function () {
        TK.clearSession();
        TK.renderHeader();
        document.dispatchEvent(new CustomEvent("tk:signed-out"));
      });
      slot.appendChild(who);
      slot.appendChild(out);
    } else {
      var login = TK.el("a", { href: "/login" }, "Log in");
      login.className = "btn btn-ghost btn-sm";
      var signup = TK.el("a", { href: "/signup" }, "Sign up");
      signup.className = "btn btn-primary btn-sm";
      slot.appendChild(login);
      slot.appendChild(signup);
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    TK.renderHeader();
    var here = location.pathname;
    document.querySelectorAll(".site-nav a").forEach(function (a) {
      if (a.getAttribute("href") === here) {
        a.setAttribute("aria-current", "page");
      }
    });
  });

  window.TK = TK;
})();
