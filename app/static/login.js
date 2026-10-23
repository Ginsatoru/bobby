"use strict";
const $ = (id) => document.getElementById(id);
const form = $("login");
const error = $("error");
const btn = $("submit");
const NOTICES = {
  out: "You've been signed out.",
  all: "You've been signed out on all devices.",
  expired: "Your session expired. Please sign in again.",
};

const reason = new URLSearchParams(location.search).get("r");
if (NOTICES[reason]) {
  $("notice").textContent = NOTICES[reason];
  $("notice").hidden = false;
  history.replaceState(null, "", "/login.html");
}
fetch("/api/me").then((r) => { if (r.ok) location.replace("/"); }).catch(() => {});

function setButton(text, cls = "") {
  btn.className = "btn dark " + cls;
  $("submit-text").textContent = text;
}

function fail(message) {
  error.textContent = message;
  form.classList.remove("shake");
  void form.offsetWidth;
  form.classList.add("shake");
  setButton("Sign in");
  btn.disabled = false;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  error.textContent = "";
  $("notice").hidden = true;
  btn.disabled = true;
  setButton("Signing in…", "loading");
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      setButton(`Welcome, ${body.username}`, "success");
      setTimeout(() => form.classList.add("leaving"), 500);
      setTimeout(() => location.replace("/"), 850);
      return;
    }
    fail(typeof body.detail === "string" ? body.detail : "Sign in failed.");
  } catch {
    fail("Can't reach Bobby's server.");
  }
});