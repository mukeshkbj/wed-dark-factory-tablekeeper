/* Tablekeeper — /signup and /login. */
(function () {
  "use strict";

  var el = TK.el;
  var errorSlot = document.getElementById("auth-error-slot");

  function showError(text) {
    // auth-error exists only while an error exists
    errorSlot.innerHTML = "";
    errorSlot.appendChild(el("p", {
      "data-testid": "auth-error",
      className: "inline-msg msg-error",
      role: "alert",
    }, text));
  }

  function clearError() { errorSlot.innerHTML = ""; }

  function handle(path, body, button) {
    clearError();
    button.disabled = true;
    TK.api(path, { method: "POST", body: body }).then(function (res) {
      button.disabled = false;
      if (res.ok && res.body && res.body.token) {
        TK.saveSession(res.body.token, res.body.display_name);
        location.href = "/";
        return;
      }
      showError(TK.errorMessage(res, "That did not work. Please try again."));
    }).catch(function () {
      button.disabled = false;
      showError("We could not reach the service. Please try again.");
    });
  }

  var signupForm = document.getElementById("signup-form");
  if (signupForm) {
    signupForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = signupForm.querySelector('[data-testid="signup-submit"]');
      handle("/auth/signup", {
        email: document.getElementById("signup-email").value,
        password: document.getElementById("signup-password").value,
        display_name: document.getElementById("signup-display-name").value,
      }, btn);
    });
  }

  var loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = loginForm.querySelector('[data-testid="login-submit"]');
      handle("/auth/login", {
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value,
      }, btn);
    });
  }
})();
