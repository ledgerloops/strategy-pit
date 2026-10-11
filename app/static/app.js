"use strict";

(() => {
  const screen = document.querySelector("#screen");
  const notice = document.querySelector("#notice");
  const connection = document.querySelector("#connection");
  let token = "";
  try { token = sessionStorage.getItem("ledgerloops.testnet.token") || ""; } catch (_) { /* Storage can be disabled. */ }
  let state = null, online = false, busy = false, lastSeen = null, refreshing = false;
  let sessionGeneration = 0;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const amount = value => `${BigInt(value).toLocaleString()} TEST`;
  const balanceText = value => Number(value) < 0 ? `You owe ${amount(-Number(value))}` : Number(value) > 0 ? `Owes you ${amount(value)}` : "Settled · 0 TEST";
  const page = () => location.hash.slice(1) || "overview";
  const intro = (title, description) => `<h1 id="title">${esc(title)}</h1><p class="muted">${esc(description)}</p>`;
  const disabled = () => !online || busy || state?.paused;
  const approvalReady = p => !p.approved && p.status === "pending";
  const statusText = p => p.status === "committed" ? ((p.cycle_complete || state?.receipts?.some(r => r.id === p.id && r.cycle_complete)) ? "Confirmed by all participants" : "Applied here · waiting for all participants") : p.approved ? `Your approval recorded · ${p.status}` : String(p.status).replaceAll("_", " ");

  function announce(text, error = false) {
    notice.textContent = text;
    notice.classList.toggle("error", error);
  }

  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST", cache: "no-store",
        credentials: "omit", signal: controller.signal,
        headers: {Authorization: `Bearer ${token}`, ...(body === undefined ? {} : {"Content-Type": "application/json"})},
        ...(body === undefined ? {} : {body: JSON.stringify(body)})
      });
      const data = await response.json();
      if (!response.ok) {
        const error = new Error(typeof data.error === "string" ? data.error : `Node request failed (${response.status}).`);
        error.status = response.status;
        throw error;
      }
      return data;
    } finally { clearTimeout(timeout); }
  }

  function updateConnection() {
    connection.classList.toggle("stale", !online);
    connection.textContent = !state ? (token ? "Connecting to this node…" : "Not connected") :
      `${online ? "Connected" : "OFFLINE / STALE — actions disabled"} · ${state.node} · last observed ${lastSeen.toLocaleTimeString()}${state.paused ? " · new clearing paused" : ""}`;
  }

  async function refresh(manual = false) {
    if (!token || refreshing) return;
    refreshing = true;
    const generation = sessionGeneration;
    try {
      const next = await api("/api/state");
      if (generation !== sessionGeneration) return;
      if (next.balances?.some(b => !Number.isSafeInteger(b.balance)) || next.mode !== "testnet" || next.unit !== "TEST" || typeof next.node !== "string" || !Array.isArray(next.balances) || !Array.isArray(next.proposals)) {
        throw new Error("Unsupported node response. This client only supports TEST testnets.");
      }
      const changed = JSON.stringify(next) !== JSON.stringify(state);
      const wasOffline = !online;
      state = next; online = true; lastSeen = new Date();
      if (changed || wasOffline || manual) render(); else updateConnection();
      if (wasOffline && !manual) announce("Connected. Displayed state has been refreshed from your node.");
      if (manual) announce("Refreshed from your node. Pending work stays pending until settlement evidence arrives.");
    } catch (error) {
      if (generation !== sessionGeneration) return;
      online = false;
      if (error.status === 401 || error.status === 403) {
        token = ""; state = null;
        try { sessionStorage.removeItem("ledgerloops.testnet.token"); } catch (_) {}
      }
      render();
      announce(error.name === "AbortError" ? "Your node did not respond. Outcomes may be uncertain; reconnect and refresh." : error.message, true);
    } finally { refreshing = false; }
  }

  function changesTable(changes) {
    if (!Array.isArray(changes) || !changes.length) return "<p>No local balance changes available yet.</p>";
    return `<div class="table-wrap"><table><caption>Your balance changes · TEST units</caption><thead><tr><th>Peer</th><th>Before</th><th>After</th></tr></thead><tbody>${changes.map(c => `<tr><td>${esc(c.peer)}</td><td>${esc(balanceText(c.before))}</td><td>${esc(balanceText(c.after))}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function proposalCard(p) {
    const approve = approvalReady(p);
    return `<article class="card ${["committed","completed"].includes(p.status) ? "completed" : "pending"}"><h2>Clear ${esc(amount(p.amount))}</h2><span class="tag">${esc(statusText(p))}</span><p class="subtle">Proposal <code>${esc(p.id)}</code></p>${changesTable(p.changes)}${approve ? `<form data-approve="${esc(p.id)}" data-digest="${esc(p.digest)}"><label class="consent"><input type="checkbox" name="consent" required ${disabled() ? "disabled" : ""}> I approve these exact changes to my test balances.</label><button type="submit" ${disabled() ? "disabled" : ""}>Approve test clearing</button><button type="button" class="secondary" data-decline="${esc(p.id)}" data-digest="${esc(p.digest)}" ${!online || busy ? "disabled" : ""}>Decline proposal</button><p class="subtle">Approval permits these changes. Reserved amounts remain unavailable while a settlement outcome is pending.</p></form>` : !["committed","completed","aborted","rejected","expired"].includes(p.status) ? "<p>Waiting for participants and settlement evidence. Closing this app does not cancel the operation.</p>" : ""}</article>`;
  }

  function render() {
    updateConnection();
    document.querySelectorAll("nav a").forEach(a => {
      if (a.hash === `#${page()}`) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (!state) {
      screen.innerHTML = intro("Your node. Your say.", "Connect to the test node serving this page. No live money or obligations belong here.") +
        `<form id="connect" class="card"><h2>Connect to this test node</h2><p>Endpoint: <code>${esc(location.origin)}</code></p><label for="token">Node access token</label><input id="token" name="token" type="password" autocomplete="off" required spellcheck="false" aria-describedby="token-help"><p id="token-help" class="subtle">Use the test token supplied by the network operator. It stays in this browser tab’s session and is sent only to this origin.</p><button type="submit" ${busy ? "disabled" : ""}>Connect</button></form><aside>The operator of this experimental node can inspect its database and act with its credentials. This is not a production custody or signing system.</aside>`;
      return;
    }
    const balances = state.balances;
    const proposals = state.proposals;
    const receipts = state.receipts || [];
    const owes = balances.reduce((sum, b) => sum + (b.balance < 0 ? -BigInt(b.balance) : 0n), 0n);
    const owed = balances.reduce((sum, b) => sum + (b.balance > 0 ? BigInt(b.balance) : 0n), 0n);
    const views = {
      overview: () => intro(`Hello, ${state.node}.`, "Your direct relationships. Your approval. Test clearing with no bank transfer.") +
        `<div class="card"><div class="row"><span>You owe</span><strong class="big">${esc(amount(owes))}</strong></div><div class="row"><span>You are owed</span><strong class="big">${esc(amount(owed))}</strong></div><p>Net position <strong>${esc(amount(owed - owes))}</strong></p><small>Recorded local balances. In-flight clearing can temporarily leave counterparties out of sync.</small></div><div class="card"><h2>${proposals.filter(approvalReady).length} proposals need your approval</h2><p>Review your before and after balances before permitting any test clearing.</p><a class="button" href="#clearing">Review clearing</a></div><p>${esc(state.outbox_pending ?? 0)} outgoing messages awaiting delivery.</p>`,
      peers: () => intro("People you trade with", "Only balances held by your node appear here. New search stops across a zero balance.") +
        `<div class="card">${balances.length ? balances.map(b => `<div class="row"><strong>${esc(b.peer)}</strong><span>${esc(balanceText(b.balance))}${b.reserved_by ? `<br><small>Reserved for pending clearing</small>` : ""}</span></div>`).join("") : "<p>No configured test peers yet.</p>"}</div><aside>Peer identities and starting test balances are configured by the network operator for this first release. Invitations and ledger imports are not available yet.</aside>`,
      clearing: () => intro("Find a loop. Agree the changes.", "Discovery uses neighbour messages. Finding a loop does not approve or settle it.") +
        `<form id="discover" class="card"><h2>Search for test clearing</h2><label for="amount">Maximum amount (whole TEST units)</label><input id="amount" name="amount" type="number" min="1" max="1000000000" step="1" value="1" required ${disabled() ? "disabled" : ""}><button type="submit" ${disabled() ? "disabled" : ""}>Discover a loop</button>${state.paused ? "<p>New clearing is paused. Resume in Your node.</p>" : ""}</form>${(state.searches || []).length ? `<div class="card"><h2>Search progress</h2>${state.searches.slice(0,5).map(s => `<p>${esc(s.status === "no_cycle_on_path" ? "No loop found on this path. Other paths may still contain opportunities." : s.status === "cycle_found" ? "Loop found — review participant proposals below." : "Searching — waiting for neighbour messages.")}</p>`).join("")}</div>` : ""}${proposals.length ? proposals.slice().reverse().map(proposalCard).join("") : "<p class=\"empty\">No proposals yet. Discovery may finish without finding a loop.</p>"}`,
      activity: () => intro("Activity and receipts", "A recorded local completion is distinct from approval or an unanswered request.") +
        (receipts.length ? receipts.slice().reverse().map(r => `<article class="card ${r.cycle_complete ? "completed" : "pending"}"><h2>Test receipt</h2><span class="tag">${esc(statusText(r))}</span><p><code>${esc(r.id)}</code></p>${changesTable(r.changes)}<button data-export="${esc(r.id)}" ${!online || busy ? "disabled" : ""}>Download receipt JSON</button><p class="subtle">Local testnet journal evidence. Not a bank payment or production settlement certificate.</p></article>`).join("") : "<p class=\"empty\">No receipts returned by your node.</p>") + `<h2>Proposal history</h2>${proposals.length ? proposals.slice().reverse().map(p => `<div class="card"><code>${esc(p.id)}</code><p>${esc(statusText(p))}</p></div>`).join("") : "<p>No proposals recorded.</p>"}`,
      settings: () => intro("Your node. Your permissions.", "The node exchanges messages while your browser is closed.") +
        `<div class="card"><div class="row"><strong>Node identity</strong><span class="node-id">${esc(state.node)}</span></div><div class="row"><strong>Mode / unit</strong><span>TESTNET / TEST</span></div><div class="row"><strong>Approval policy</strong><span>Ask each participant</span></div><button data-action="pause" ${!online || busy ? "disabled" : ""}>${state.paused ? "Resume new clearing" : "Pause new clearing"}</button><p>Pausing stops new work. Already admitted settlement messages still need recovery.</p></div><div class="card"><h2>Connection</h2><p><code>${esc(location.origin)}</code></p><button class="secondary" data-action="refresh" ${busy ? "disabled" : ""}>Refresh node state</button><button class="secondary" data-action="disconnect">Disconnect this browser</button><p class="subtle">Disconnect clears this tab’s token and displayed state. It does not revoke the operator token, stop the node, or cancel pending clearing.</p></div><aside>Test-only shared-secret authentication. The node operator holds the credentials and database. Backups, identity rotation and production key custody require further implementation and review.</aside>`
    };
    screen.innerHTML = (views[page()] || views.overview)();
  }

  async function mutate(path, body, success) {
    if (busy || !online) return;
    busy = true; render();
    try {
      const result = await api(path, body);
      announce(success(result));
      await refresh();
    } catch (error) {
      online = false;
      announce(`Request outcome not confirmed: ${error.message} Reconnect and refresh before taking another action.`, true);
    } finally { busy = false; render(); }
  }

  document.addEventListener("submit", async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    if (form.id === "connect") {
      if (busy) return;
      token = new FormData(form).get("token").trim();
      if (!token) return;
      try { sessionStorage.setItem("ledgerloops.testnet.token", token); } catch (_) {}
      await refresh();
      return;
    }
    if (form.id === "discover") {
      const value = Number(new FormData(form).get("amount"));
      if (!Number.isSafeInteger(value) || value <= 0 || value > 1000000000) {
        announce("Enter a positive whole amount up to 1,000,000,000 TEST.", true); return;
      }
      await mutate("/api/discover", {amount: value}, r => `Discovery accepted (${r.id}). Waiting for neighbour responses; no balances have been cleared by this request alone.`);
    } else if (form.dataset.approve && new FormData(form).get("consent")) {
      const id = form.dataset.approve;
      await mutate(`/api/proposals/${encodeURIComponent(id)}/approve`, {digest: form.dataset.digest}, () => "The node accepted your approval request. Check the proposal status for settlement progress; approval is not completion.");
    }
  });

  document.addEventListener("click", async event => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    if (button.dataset.action === "disconnect") {
      sessionGeneration++; token = ""; state = null; online = false; lastSeen = null;
      try { sessionStorage.removeItem("ledgerloops.testnet.token"); } catch (_) {}
      render(); announce("Browser disconnected. The node continues any pending settlement work.");
    } else if (button.dataset.action === "refresh") await refresh(true);
    else if (button.dataset.action === "pause") {
      await mutate("/api/pause", {paused: !state.paused}, r => r.paused ? "New clearing paused. Recovery of pending work continues." : "New clearing resumed.");
    } else if (button.dataset.decline) {
      await mutate(`/api/proposals/${encodeURIComponent(button.dataset.decline)}/decline`, {digest: button.dataset.digest}, () => "Decline request accepted. Reservations remain until the node records a safe abort outcome; this is not a completed cancellation yet.");
    } else if (button.dataset.export) {
      try {
        const receipt = await api(`/api/receipts/${encodeURIComponent(button.dataset.export)}`);
        const url = URL.createObjectURL(new Blob([JSON.stringify({mode:"testnet", unit:"TEST", node:state.node, receipt}, null, 2)], {type:"application/json"}));
        const link = document.createElement("a"); link.href = url;
        link.download = `ledgerloops-test-receipt-${String(button.dataset.export).replace(/[^a-zA-Z0-9_-]/g, "_")}.json`;
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        announce("Downloaded your node’s test receipt. It contains local balance information; share it carefully.");
      } catch (error) { announce(`Receipt unavailable: ${error.message}`, true); }
    }
  });

  window.addEventListener("hashchange", render);
  window.addEventListener("offline", () => { online = false; render(); announce("Browser offline. Displayed balances may be stale. Pending requests need recovery, not a blind resubmission.", true); });
  window.addEventListener("online", () => refresh());
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  setInterval(() => { if (!document.hidden && !busy) refresh(); }, 3000);
  render();
  if (token) refresh();
})();
