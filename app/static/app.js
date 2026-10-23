"use strict";

const $ = (id) => document.getElementById(id);
const el = {
  app: $("app"), main: $("main"), sidebar: $("sidebar"), history: $("history"),
  search: $("search"), stage: document.querySelector(".stage"), ctx: $("ctx-wrap"), title: $("title"), thread: $("thread"), messages: $("messages"),
  form: $("composer"), input: $("input"), context: $("context"), send: $("send"),
  status: $("status"), statusText: $("status-text"), hello: $("hello"), ask: $("ask"),
};
const ICON = {
  send: '<svg class="i" viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  stop: '<svg class="i" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>',
  close: '<svg class="i" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  copy: '<svg class="i" viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>',
  check: '<svg class="i" viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg>',
  more: '<svg class="i" viewBox="0 0 24 24"><path d="M5 12h.01M12 12h.01M19 12h.01" stroke-width="3"/></svg>',
};
const state = { id: null, mode: "chat", count: 0, busy: false, abort: null };
let historyItems = [];

/* ---------- helpers ---------- */

function div(className, text = "") {
  const node = document.createElement("div");
  node.className = className;
  node.textContent = text;
  return node;
}

function toLogin() {
  location.href = "/login.html?r=expired";
  return new Promise(() => {}); // page is leaving; never settle
}

async function errorMessage(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch { /* not JSON */ }
  return `Request failed (${res.status}).`;
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (res.status === 401) return toLogin();
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function readLines(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
  }
}

const scrollDown = () => { el.messages.scrollTop = el.messages.scrollHeight; };
const isMobile = () => !!window.matchMedia?.("(max-width: 720px)").matches;

/* ---------- messages ---------- */

function makeMessage(role, text) {
  const wrap = div("msg " + role);
  const bubble = div("bubble", text);
  wrap.append(div("role", role === "user" ? "You" : "Bobby"), bubble);
  el.thread.appendChild(wrap);
  scrollDown();
  return { wrap, bubble };
}

function addMessage(role, text) {
  const msg = makeMessage(role, text);
  state.count++;
  updateComposer();
  return msg;
}

function addError(text) {
  const msg = makeMessage("bot", text);
  msg.bubble.classList.add("error");
  return msg;
}

function addCopy(msg) {
  const btn = document.createElement("button");
  const label = (icon, text) => { btn.innerHTML = icon + text; };
  btn.type = "button";
  btn.className = "link";
  label(ICON.copy, "Copy");
  btn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(msg.bubble.textContent);
      label(ICON.check, "Copied");
    } catch {
      label(ICON.copy, "Copy failed");
    }
    setTimeout(() => label(ICON.copy, "Copy"), 1500);
  };
  msg.wrap.appendChild(btn);
}

function showEmpty() {
  el.thread.replaceChildren();
}

function updateComposer() {
  const empty = state.count === 0;
  const email = state.mode === "email";
  const firstEmail = email && empty;
  el.main.classList.toggle("is-empty", empty);
  el.ctx.classList.toggle("open", firstEmail);
  el.ctx.inert = !firstEmail;
  el.input.placeholder = firstEmail ? "Paste customer message"
    : email ? "Ask for changes"
    : "Ask Bobby anything…";
  el.input.rows = firstEmail ? 4 : empty ? 2 : 1;
  el.hello.textContent = email ? "Email assistant" : "Hello Support team";
  el.ask.textContent = email ? "Reply to a customer" : "How can Bobby help you today?";
  $("mode-chat").classList.toggle("active", !email);
  $("mode-email").classList.toggle("active", email);
  $("export").disabled = empty;
  autosize();
}

function autosize() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 180) + "px";
}

function setBusy(busy) {
  state.busy = busy;
  el.send.innerHTML = busy ? ICON.stop : ICON.send;
  el.send.setAttribute("aria-label", busy ? "Stop" : "Send");
}

/* ---------- confirm dialog ---------- */

function confirmDialog(title, text, okLabel) {
  const dlg = $("confirm");
  $("confirm-title").textContent = title;
  $("confirm-text").textContent = text;
  $("confirm-ok").textContent = okLabel;
  dlg.returnValue = "";
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.showModal();
  });
}

$("confirm").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) e.currentTarget.close();
});

/* ---------- sidebar ---------- */

function toggleSidebar() {
  if (isMobile()) el.sidebar.classList.toggle("open");
  else el.app.classList.toggle("collapsed");
}

function closeSidebar() { el.sidebar.classList.remove("open"); }

/* ---------- conversations ---------- */

function replay(node) {
  node.classList.remove("swap");
  void node.offsetWidth;
  node.classList.add("swap");
}

function startNew(mode, prompt = "") {
  const changed = state.mode !== mode || state.count > 0;
  state.abort?.abort();
  Object.assign(state, { id: null, mode, count: 0 });
  el.title.textContent = mode === "email" ? "New email draft" : "New chat";
  showEmpty();
  el.input.value = prompt;
  updateComposer();
  closeSidebar();
  renderHistory();
  if (changed) replay(el.stage);
  el.input.focus();
}

async function openConversation(id) {
  state.abort?.abort();
  try {
    const conv = await api(`/api/conversations/${id}`);
    const changed = state.id !== conv.id;
    Object.assign(state, { id: conv.id, mode: conv.mode, count: 0 });
    el.title.textContent = conv.title;
    el.thread.replaceChildren();
    for (const m of conv.messages) {
      const role = m.role === "user" ? "user" : "bot";
      const msg = addMessage(role, m.content);
      if (role === "bot") addCopy(msg);
    }
    updateComposer();
    renderHistory();
    closeSidebar();
    if (changed) { replay(el.stage); replay(el.title); }
  } catch (err) {
    addError(err.message);
  }
}

async function removeConversation(item) {
  if (!(await confirmDialog("Delete chat?", `"${item.title}" will be removed.`, "Delete"))) return;
  try {
    await api(`/api/conversations/${item.id}`, { method: "DELETE" });
  } catch (err) {
    return addError(err.message);
  }
  if (state.id === item.id) startNew(state.mode);
  loadHistory();
}

function groupLabel(ts) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  if (ts >= today) return "Today";
  if (ts >= today - 86400) return "Yesterday";
  if (ts >= today - 7 * 86400) return "Previous 7 days";
  return "Older";
}

function renderHistory() {
  const query = el.search.value.trim().toLowerCase();
  const nodes = [];
  let last = "";
  for (const item of historyItems) {
    if (query && !item.title.toLowerCase().includes(query)) continue;
    const label = groupLabel(item.updated_at);
    if (label !== last) { nodes.push(div("group", label)); last = label; }
    const row = div("history-item" + (item.id === state.id ? " active" : ""));
    const open = document.createElement("button");
    open.type = "button";
    open.className = "open";
    open.textContent = item.title;
    open.onclick = () => openConversation(item.id);
    const del = document.createElement("button");
    del.type = "button";
    del.className = "del";
    del.innerHTML = ICON.close;
    del.title = "Delete conversation";
    del.setAttribute("aria-label", "Delete conversation");
    del.onclick = () => removeConversation(item);
    row.append(open, del);
    nodes.push(row);
  }
  el.history.replaceChildren(...nodes);
}

async function loadHistory() {
  try { historyItems = await api("/api/conversations"); } catch { return; }
  renderHistory();
}

/* ---------- sending ---------- */

async function send() {
  const message = el.input.value.trim();
  if (!message) return;
  const context = el.context.value.trim();
  el.input.value = "";
  el.context.value = "";
  autosize();
  setBusy(true);

  let bot = null;
  let text = "";
  let started = false;
  let saveCase = false;
  const fail = (msg) => {
    if (bot && !text) {
      bot.bubble.classList.remove("pending");
      bot.bubble.classList.add("error");
      bot.bubble.textContent = msg;
    } else {
      addError(msg);
    }
    text = text || "\0";
  };

  state.abort = new AbortController();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: state.id, mode: state.mode, message, context }),
      signal: state.abort.signal,
    });
    if (res.status === 401) return toLogin();
    if (!res.ok) throw new Error(await errorMessage(res));
    await readLines(res, (ev) => {
      if (ev.type === "meta") {
        started = true;
        state.id = ev.conversation_id;
        el.title.textContent = ev.title;
        addMessage("user", ev.user_message);
        bot = addMessage("bot", "Thinking…");
        bot.bubble.classList.add("pending");
      } else if (ev.type === "token") {
        if (!text) {
          bot.bubble.classList.remove("pending");
          bot.bubble.textContent = "";
        }
        text += ev.text;
        bot.bubble.textContent = text;
        scrollDown();
      } else if (ev.type === "done") {
        saveCase = !!ev.save_case;
      } else if (ev.type === "error") {
        fail(ev.message);
      }
    });
  } catch (err) {
    if (err.name !== "AbortError") {
      fail(err instanceof TypeError
        ? "Can't reach Bobby's server. Check that run.bat is still running."
        : err.message);
      if (!started) { el.input.value = message; el.context.value = context; autosize(); }
    }
  } finally {
    if (bot && bot.bubble.classList.contains("pending")) bot.wrap.remove();
    else if (bot && text && text !== "\0" && !bot.bubble.classList.contains("error")) {
      addCopy(bot);
      if (saveCase && state.id) saveCaseFromChat(bot, state.id);
    }
    state.abort = null;
    setBusy(false);
    loadHistory();
  }
}

/* ---------- knowledge ---------- */

const KB_LABEL = { saved: "Saved to knowledge", duplicate: "Already in knowledge", updated: "Knowledge updated" };
const feed = { files: [] };

const kbNote = (status, text) => div("kb-note " + status, text);

async function saveCaseFromChat(msg, id) {
  const note = kbNote("saving", "Saving to knowledge…");
  msg.wrap.appendChild(note);
  scrollDown();
  try {
    const r = await api("/api/knowledge/from-chat", { method: "POST", body: JSON.stringify({ conversation_id: id }) });
    if (r.status === "skipped") return note.remove();
    note.className = "kb-note " + r.status;
    note.textContent = `${KB_LABEL[r.status]}: ${r.title}`;
  } catch (err) {
    note.className = "kb-note error";
    note.textContent = `Couldn't save to knowledge. ${err.message}`;
  }
}

function renderFeedFiles() {
  $("feed-files").replaceChildren(...feed.files.map((file, i) => {
    const chip = div("file-chip", file.name);
    const x = document.createElement("button");
    x.type = "button";
    x.innerHTML = ICON.close;
    x.setAttribute("aria-label", `Remove ${file.name}`);
    x.onclick = () => { feed.files.splice(i, 1); renderFeedFiles(); };
    chip.appendChild(x);
    return chip;
  }));
}

function addFeedFiles(list) {
  const files = [...list];
  const ok = files.filter((f) => /\.(txt|md)$/i.test(f.name) || f.type === "text/plain");
  feed.files.push(...ok);
  renderFeedFiles();
  $("feed-results").replaceChildren(
    ...(ok.length < files.length ? [kbNote("error", "Only .txt or .md files can be added.")] : []));
}

function toast(kind, text) {
  const node = kbNote(kind, text);
  node.classList.add("toast");
  node.title = "Dismiss";
  node.onclick = () => node.remove();
  $("toasts").appendChild(node);
  return node;
}

function settleToast(node, kind, text) {
  node.className = `kb-note toast ${kind}`;
  node.textContent = text;
  setTimeout(() => {
    node.classList.add("out");
    setTimeout(() => node.remove(), 250);
  }, kind === "error" ? 8000 : 5000);
}

function feedSummary(results) {
  if (!results.length) return ["error", "No problem with a fix found in that text."];
  if (results.length === 1) return [results[0].status, `${KB_LABEL[results[0].status]}: ${results[0].title}`];
  const saved = results.filter((r) => r.status === "saved").length;
  const known = results.length - saved;
  const parts = [];
  if (saved) parts.push(`Added ${saved} case${saved > 1 ? "s" : ""} to knowledge`);
  if (known) parts.push(`${known} already known`);
  return [saved ? "saved" : "duplicate", parts.join(" · ")];
}

function openFeed() {
  $("feed-results").replaceChildren();
  closeSidebar();
  $("feed").showModal();
  $("feed-text").focus();
}

async function submitFeed() {
  const out = $("feed-results");
  const parts = [$("feed-text").value.trim()];
  try {
    for (const file of feed.files) parts.push((await file.text()).trim());
  } catch {
    return out.replaceChildren(kbNote("error", "Couldn't read one of the files."));
  }
  const text = parts.filter(Boolean).join("\n\n");
  if (!text) return out.replaceChildren(kbNote("error", "Paste some text or attach a file first."));
  $("feed-text").value = "";
  feed.files = [];
  renderFeedFiles();
  $("feed").close();
  const note = toast("saving", "Adding to knowledge…");
  try {
    const { results } = await api("/api/knowledge", { method: "POST", body: JSON.stringify({ text }) });
    settleToast(note, ...feedSummary(results));
  } catch (err) {
    settleToast(note, "error", `Couldn't add to knowledge. ${err.message}`);
  }
}

/* ---------- account ---------- */

let me = null;
let pwTarget = null; // null = my own password, otherwise a user being reset by an admin

function toggleUserMenu(open = $("user-menu").hidden) {
  $("user-menu").hidden = !open;
  $("user-btn").setAttribute("aria-expanded", String(open));
}

function leaveTo(reason) {
  el.app.classList.add("leaving");
  setTimeout(() => { location.href = `/login.html?r=${reason}`; }, 300);
}

function openPassword(target = null) {
  pwTarget = target;
  toggleUserMenu(false);
  $("pw-title").textContent = target ? `Reset password for ${target.username}` : "Change password";
  $("pw-text").textContent = target ? "They'll be signed out on all devices." : "Other devices will be signed out.";
  $("pw-current").hidden = !!target;
  for (const id of ["pw-current", "pw-new", "pw-repeat"]) $(id).value = "";
  $("pw-error").textContent = "";
  $("pw").showModal();
  $(target ? "pw-new" : "pw-current").focus();
}

async function savePassword() {
  const fresh = $("pw-new").value;
  const err = (msg) => { $("pw-error").textContent = msg; };
  if (!pwTarget && !$("pw-current").value) return err("Enter your current password.");
  if (fresh.length < 8) return err("New password must be at least 8 characters.");
  if (fresh !== $("pw-repeat").value) return err("New passwords don't match.");
  $("pw-save").disabled = true;
  try {
    if (pwTarget) {
      await api(`/api/admin/users/${pwTarget.id}/password`, { method: "POST", body: JSON.stringify({ password: fresh }) });
      adminMsg(`Password reset for ${pwTarget.username}.`);
    } else {
      await api("/api/password", { method: "POST", body: JSON.stringify({ current: $("pw-current").value, new: fresh }) });
      settleToast(toast("saved", ""), "saved", "Password changed. Other devices were signed out.");
    }
    $("pw").close();
  } catch (e) {
    err(e.message);
  }
  $("pw-save").disabled = false;
}

async function logoutAll() {
  toggleUserMenu(false);
  if (!(await confirmDialog("Sign out everywhere?", "This signs you out on every device, including this one.", "Sign out all"))) return;
  state.abort?.abort();
  try { await fetch("/api/logout-all", { method: "POST" }); } catch { /* signing out anyway */ }
  leaveTo("all");
}

/* ---------- admin ---------- */

const admin = { cases: [] };

function adminMsg(text, error = false) {
  $("admin-msg").textContent = text;
  $("admin-msg").className = "admin-msg" + (error ? " error" : "");
}

async function adminCall(path, options, success) {
  try {
    await api(path, options);
    if (success) adminMsg(success);
    return true;
  } catch (e) {
    adminMsg(e.message, true);
    return false;
  }
}

function linkBtn(label, onClick, danger = false) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "link" + (danger ? " danger" : "");
  b.textContent = label;
  b.onclick = onClick;
  return b;
}

function closeRowMenus() {
  for (const m of document.querySelectorAll(".row-menu")) m.hidden = true;
}

function rowMenu(items) {
  const wrap = div("row-more");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "icon-btn";
  btn.innerHTML = ICON.more;
  btn.title = "Actions";
  btn.setAttribute("aria-label", "Actions");
  const menu = div("row-menu");
  menu.hidden = true;
  for (const [label, onClick, danger] of items) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "menu-item" + (danger ? " danger" : "");
    item.textContent = label;
    item.onclick = () => { closeRowMenus(); onClick(); };
    menu.appendChild(item);
  }
  btn.onclick = (e) => {
    e.stopPropagation();
    const open = menu.hidden;
    closeRowMenus();
    if (!open) return;
    menu.hidden = false;
    const b = btn.getBoundingClientRect();
    const fitsBelow = b.bottom + 4 + menu.offsetHeight < window.innerHeight - 8;
    menu.style.left = `${b.right - menu.offsetWidth}px`;
    menu.style.top = `${fitsBelow ? b.bottom + 4 : b.top - 4 - menu.offsetHeight}px`;
  };
  wrap.append(btn, menu);
  return wrap;
}

const shortDate = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

async function loadUsers() {
  let users;
  try { users = await api("/api/admin/users"); } catch (e) { return adminMsg(e.message, true); }
  $("user-count").textContent = `Team · ${users.length} user${users.length === 1 ? "" : "s"}`;
  $("user-list").replaceChildren(...users.map((u) => {
    const row = div("admin-row");
    const avatar = div("avatar sm", u.username.charAt(0).toUpperCase());
    const name = div("admin-info");
    name.append(div("admin-name", u.username));
    if (u.id === me.id) name.append(div("badge", "You"));
    if (u.locked) name.append(div("badge warn", "Locked"));
    const info = div("admin-text");
    info.append(name, div("admin-meta", `${u.is_admin ? "Admin" : "Staff"} · Added ${shortDate(u.created_at)}`));
    const items = u.id === me.id ? [["Change password", () => openPassword()]] : [
      ["Reset password", () => openPassword(u)],
      ...(u.locked ? [["Unlock", async () => {
        if (await adminCall(`/api/admin/users/${u.id}/unlock`, { method: "POST" }, `${u.username} unlocked.`)) loadUsers();
      }]] : []),
      [u.is_admin ? "Remove admin" : "Make admin", async () => {
        const ok = await adminCall(`/api/admin/users/${u.id}/admin`,
          { method: "POST", body: JSON.stringify({ is_admin: !u.is_admin }) },
          `${u.username} ${u.is_admin ? "is no longer" : "is now"} an admin.`);
        if (ok) loadUsers();
      }],
      ["Delete user", async () => {
        if (!(await confirmDialog(`Delete ${u.username}?`, "Their account and all their chats will be removed. Knowledge they added stays.", "Delete"))) return;
        if (await adminCall(`/api/admin/users/${u.id}`, { method: "DELETE" }, `${u.username} deleted.`)) loadUsers();
      }, true],
    ];
    row.append(avatar, info, rowMenu(items));
    return row;
  }));
}

function showAddUser(show) {
  $("add-user").hidden = !show;
  $("toggle-add").hidden = show;
  if (show) {
    $("new-username").focus();
  } else {
    $("new-username").value = "";
    $("new-password").value = "";
    $("new-admin").checked = false;
  }
}

function renderCases() {
  const q = $("case-search").value.trim().toLowerCase();
  const shown = admin.cases.filter((c) => !q || `${c.title} ${c.problem} ${c.fix}`.toLowerCase().includes(q));
  if (!shown.length) return $("case-list").replaceChildren(div("admin-empty", q ? "No matches." : "No knowledge yet."));
  $("case-list").replaceChildren(...shown.map((c) => {
    const row = div("admin-row case");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const date = new Date(c.created_at * 1000).toLocaleDateString();
    summary.append(div("admin-name", c.title), div("admin-meta", `${c.source} · ${c.added_by || "deleted user"} · ${date}`));
    details.append(summary, div("case-body", [`Problem: ${c.problem}`, c.cause && `Cause: ${c.cause}`, `Fix: ${c.fix}`].filter(Boolean).join("\n\n")));
    row.append(details, rowMenu([
      ["Edit case", () => openCaseEdit(c)],
      ["Delete case", async () => {
        if (!(await confirmDialog("Delete case?", `"${c.title}" will be removed from Bobby's knowledge.`, "Delete"))) return;
        if (await adminCall(`/api/admin/cases/${c.id}`, { method: "DELETE" }, "Case deleted.")) loadCases();
      }, true],
    ]));
    return row;
  }));
}

let editingCase = null;
const CASE_FIELDS = ["title", "problem", "cause", "fix"];

function openCaseEdit(c) {
  editingCase = c;
  for (const f of CASE_FIELDS) $(`case-${f}`).value = c[f];
  $("case-error").textContent = "";
  $("case-dlg").showModal();
  $("case-title").focus();
}

async function saveCase() {
  const body = Object.fromEntries(CASE_FIELDS.map((f) => [f, $(`case-${f}`).value.trim()]));
  if (!body.title || !body.problem || !body.fix) {
    $("case-error").textContent = "Title, problem and fix can't be empty.";
    return;
  }
  $("case-save").disabled = true;
  try {
    await api(`/api/admin/cases/${editingCase.id}`, { method: "PUT", body: JSON.stringify(body) });
    $("case-dlg").close();
    adminMsg("Case updated.");
    loadCases();
  } catch (e) {
    $("case-error").textContent = e.message;
  }
  $("case-save").disabled = false;
}

async function loadCases() {
  try { admin.cases = await api("/api/admin/cases"); } catch (e) { return adminMsg(e.message, true); }
  renderCases();
}

function showTab(name) {
  for (const b of document.querySelectorAll("#admin .tabs .chip")) b.classList.toggle("active", b.dataset.tab === name);
  $("tab-users").hidden = name !== "users";
  $("tab-cases").hidden = name !== "cases";
  adminMsg("");
  showAddUser(false);
  if (name === "users") loadUsers(); else loadCases();
}

function openAdmin() {
  toggleUserMenu(false);
  closeSidebar();
  $("admin").showModal();
  showTab("users");
}

async function addUser() {
  const username = $("new-username").value.trim();
  const password = $("new-password").value;
  if (!username) return adminMsg("Enter a username.", true);
  if (password.length < 8) return adminMsg("Password must be at least 8 characters.", true);
  const ok = await adminCall("/api/admin/users",
    { method: "POST", body: JSON.stringify({ username, password, is_admin: $("new-admin").checked }) },
    `${username} added.`);
  if (!ok) return;
  showAddUser(false);
  loadUsers();
}

/* ---------- status ---------- */

function setStatus(kind, label, hint) {
  el.status.className = "status " + kind;
  el.statusText.textContent = label;
  el.status.title = hint || "Check connection";
}

async function checkStatus() {
  setStatus("", "Checking…");
  try {
    const s = await api("/api/status");
    if (!s.connected) setStatus("bad", "Ollama not running", "Start the Ollama app, then click to check again.");
    else if (!s.model_installed) setStatus("warn", `${s.model} not installed`, `Run: ollama pull ${s.model}`);
    else setStatus("ok", `${s.model} · Connected`);
  } catch {
    setStatus("bad", "Server unreachable", "Bobby's server isn't responding.");
  }
}

/* ---------- export ---------- */

function exportChat() {
  const parts = [...el.thread.querySelectorAll(".msg")]
    .filter((m) => !m.querySelector(".bubble.error, .bubble.pending"))
    .map((m) => `${m.querySelector(".role").textContent}:\n${m.querySelector(".bubble").textContent}`);
  if (!parts.length) return;
  const name = el.title.textContent.replace(/[^\w -]+/g, "").trim() || "bobby-chat";
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([parts.join("\n\n")], { type: "text/plain" }));
  link.download = name + ".txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

/* ---------- wiring ---------- */

el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (state.busy) state.abort?.abort();
  else send();
});
el.input.addEventListener("input", autosize);
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!state.busy) send();
  }
});
el.search.addEventListener("input", renderHistory);
$("new-chat").onclick = () => startNew("chat");
$("new-email").onclick = () => startNew("email");
$("mode-chat").onclick = () => { if (state.mode !== "chat" || state.count) startNew("chat"); };
$("mode-email").onclick = () => { if (state.mode !== "email" || state.count) startNew("email"); };
$("collapse").onclick = toggleSidebar;
$("menu").onclick = toggleSidebar;
$("export").onclick = exportChat;
$("feed-open").onclick = openFeed;
$("feed-close").onclick = () => $("feed").close();
$("feed").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
$("feed-form").addEventListener("submit", (e) => { e.preventDefault(); submitFeed(); });
$("feed-file").onchange = (e) => {
  addFeedFiles(e.target.files);
  e.target.value = "";
};
$("feed").addEventListener("dragover", (e) => {
  e.preventDefault();
  $("feed").classList.add("dragging");
});
$("feed").addEventListener("dragleave", (e) => {
  if (!$("feed").contains(e.relatedTarget)) $("feed").classList.remove("dragging");
});
$("feed").addEventListener("drop", (e) => {
  e.preventDefault();
  $("feed").classList.remove("dragging");
  if (e.dataTransfer.files.length) addFeedFiles(e.dataTransfer.files);
});
$("logout").onclick = async () => {
  if (!(await confirmDialog("Sign out?", "You'll need to sign in again to use Bobby.", "Sign out"))) return;
  state.abort?.abort();
  try { await fetch("/api/logout", { method: "POST" }); } catch { /* signing out anyway */ }
  leaveTo("out");
};
$("user-btn").onclick = (e) => { e.stopPropagation(); toggleUserMenu(); };
document.addEventListener("click", (e) => {
  if (!$("user-menu").contains(e.target)) toggleUserMenu(false);
  closeRowMenus();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggleUserMenu(false); });
$("open-password").onclick = () => openPassword();
$("logout-all").onclick = logoutAll;
$("open-admin").onclick = openAdmin;
$("pw-cancel").onclick = () => $("pw").close();
$("pw-form").addEventListener("submit", (e) => { e.preventDefault(); savePassword(); });
$("admin-close").onclick = () => $("admin").close();
for (const b of document.querySelectorAll("#admin .tabs .chip")) b.onclick = () => showTab(b.dataset.tab);
$("add-user").addEventListener("submit", (e) => { e.preventDefault(); addUser(); });
$("toggle-add").onclick = () => showAddUser(true);
$("user-list").addEventListener("scroll", closeRowMenus);
$("cancel-add").onclick = () => showAddUser(false);
$("case-search").addEventListener("input", renderCases);
$("case-cancel").onclick = () => $("case-dlg").close();
$("case-form").addEventListener("submit", (e) => { e.preventDefault(); saveCase(); });
el.messages.addEventListener("click", closeSidebar);
el.status.onclick = checkStatus;
for (const card of document.querySelectorAll(".suggest")) {
  card.onclick = () => {
    if (card.dataset.action === "email") startNew("email");
    else startNew("chat", card.dataset.prompt);
    autosize();
  };
}
$("clear").onclick = async () => {
  if (state.busy) return;
  if (state.count && !(await confirmDialog("Clear chat?", "All messages in this conversation will be removed.", "Clear"))) return;
  try {
    if (state.id) await api(`/api/conversations/${state.id}/clear`, { method: "POST" });
  } catch (err) {
    return addError(err.message);
  }
  state.count = 0;
  showEmpty();
  updateComposer();
};

startNew("chat");
api("/api/me").then((u) => {
  me = u;
  $("user-name").textContent = u.username;
  $("avatar").textContent = u.username.charAt(0).toUpperCase();
  $("open-admin").hidden = !u.is_admin;
}).catch(() => {});
loadHistory();
checkStatus();
setInterval(checkStatus, 30000);