"use strict";

(() => {
  const screen = document.querySelector("#screen");
  const notice = document.querySelector("#notice");
  const connection = document.querySelector("#connection");
  let token = "";
  try { token = sessionStorage.getItem("ledgerloops.testnet.token") || ""; } catch (_) { /* Storage can be disabled. */ }
  let state = null, online = false, busy = false, lastSeen = null, refreshing = false;
  let fulfillmentChecks = new Map();
  const contactDrafts = new Map();
  let sessionGeneration = 0;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const amount = value => `${BigInt(value).toLocaleString()} TEST`;
  const balanceText = value => Number(value) < 0 ? `You owe ${amount(-Number(value))}` : Number(value) > 0 ? `Owes you ${amount(value)}` : "Settled · 0 TEST";
  const page = () => location.hash.slice(1) || "overview";
  const intro = (title, description) => `<h1 id="title">${esc(title)}</h1><p class="muted">${esc(description)}</p>`;
  const disabled = () => !online || busy || state?.paused;
  const approvalReady = p => !p.approved && p.status === "pending";
  const privateProtocol = () => state?.protocol === "private-hashlock-v2";
  let searchMode = "cancellation";
  const comfortAvailable = () => privateProtocol() && state.discovery_modes?.includes("comfort");
  const protocolLabel = () => privateProtocol() ? "Private hashlock v2 · experimental" : "Legacy infrastructure test · route-visible";
  function statusText(p) {
    if (privateProtocol()) {
      const receipt = state?.receipts?.find(r => r.id === p.id) || p;
      if (p.status === "committed") return fulfillmentChecks.get(receipt.id) === "verified" ? "Applied locally · fulfillment verified" : fulfillmentChecks.get(receipt.id) === "invalid" ? "Verification failed · needs investigation" : "Applied locally · browser verification unavailable";
      return p.approved ? `Your conditional approval recorded · ${String(p.status).replaceAll("_", " ")}` : String(p.status).replaceAll("_", " ");
    }
    return p.status === "committed" ? ((p.cycle_complete || state?.receipts?.some(r => r.id === p.id && r.cycle_complete)) ? "Confirmed by all participants" : "Applied here · waiting for all participants") : p.approved ? `Your approval recorded · ${p.status}` : String(p.status).replaceAll("_", " ");
  }

  function hashlockDetails(p) {
    if (!privateProtocol()) return "";
    const receipt = state.receipts?.find(r => r.id === p.id) || p;
    const verified = fulfillmentChecks.get(receipt.id) === "verified";
    const released = receipt.status === "committed" && receipt.local_fulfilled === true;
    const explanation = verified ? "This browser verified that the released fulfillment matches the condition. Your node reports applying your local changes. This does not prove that every other node has applied theirs." : released ? "Your node reports applying the changes. This browser has not verified matching fulfillment evidence; investigate a verification failure before relying on the receipt." : p.status === "aborted" ? "Your node recorded an abort. No fulfillment was released in this receipt." : "Your approval is conditional on a matching fulfillment. The node retains reservations while it waits for a valid outcome.";
    return `<div class="card"><h3>Conditional clearing</h3><p>${explanation}</p><details><summary>Local verification details</summary><p>Condition (SHA-256)<br><code>${esc(p.condition || "Not supplied")}</code></p>${released && typeof receipt.preimage === "string" ? `<p>Released fulfillment<br><code>${esc(receipt.preimage)}</code></p><p>Browser check: ${esc(fulfillmentChecks.get(receipt.id) || "unavailable")}</p>` : "<p>No released fulfillment is displayed.</p>"}<p class="subtle">These details concern your local obligation changes. They do not list a complete route or other participants.</p></details></div>`;
  }

  async function verifyFulfillments(next) {
    const checks = new Map();
    if (next.protocol !== "private-hashlock-v2") return checks;
    for (const receipt of next.receipts || []) {
      if (receipt.status !== "committed") continue;
      if (!["sha256-context-v2","sha256-comfort-v1"].includes(receipt.hashlock_scheme)) { checks.set(receipt.id, "unavailable — unsupported verification scheme"); continue; }
      if (!receipt.local_fulfilled || !/^[a-f0-9]{64}$/.test(receipt.preimage || "") || !/^[a-f0-9]{64}$/.test(receipt.condition || "") || !/^[a-f0-9]{64}$/.test(receipt.id || "") || !Number.isSafeInteger(receipt.amount) || receipt.amount <= 0 || receipt.protocol !== "private-hashlock-v2" || receipt.unit !== "TEST") { checks.set(receipt.id, "invalid"); continue; }
      if (!globalThis.crypto?.subtle) { checks.set(receipt.id, "unavailable — a secure browser context is required"); continue; }
      const comfort = receipt.hashlock_scheme === "sha256-comfort-v1";
      if (comfort && (receipt.clearing_mode !== "comfort" || receipt.policy !== "bilateral-comfort-v1" || ![-1,1].includes(receipt.direction))) { checks.set(receipt.id,"invalid"); continue; }
      if (!comfort && ["clearing_mode","policy","direction"].some(key => key in receipt)) { checks.set(receipt.id,"invalid"); continue; }
      const context = comfort ? {amount:receipt.amount,clearing_mode:receipt.clearing_mode,direction:receipt.direction,id:receipt.id,policy:receipt.policy,preimage:receipt.preimage,protocol:receipt.protocol,unit:receipt.unit} : {amount:receipt.amount,id:receipt.id,preimage:receipt.preimage,protocol:receipt.protocol,unit:receipt.unit};
      const bytes = new TextEncoder().encode(JSON.stringify(context));
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const hash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
      checks.set(receipt.id, hash === receipt.condition ? "verified" : "invalid");
    }
    return checks;
  }

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
      `${online ? "Connected" : "OFFLINE / STALE — actions disabled"} · ${state.node} · ${protocolLabel()} · last observed ${lastSeen.toLocaleTimeString()}${state.paused ? " · new clearing paused" : ""}`;
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
      const checks = await verifyFulfillments(next);
      if (generation !== sessionGeneration) return;
      const changed = JSON.stringify(next) !== JSON.stringify(state);
      const wasOffline = !online;
      state = next; fulfillmentChecks = checks; online = true; lastSeen = new Date();
      if (changed || wasOffline || manual) render(); else updateConnection();
      if (wasOffline && !manual) announce("Connected. Displayed state has been refreshed from your node.");
      if (manual) announce("Refreshed from your node. Pending work stays pending until settlement evidence arrives.");
    } catch (error) {
      if (generation !== sessionGeneration) return;
      online = false;
      if (error.status === 401 || error.status === 403) {
        token = ""; state = null; contactDrafts.clear();
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
    return `<article class="card ${(privateProtocol() ? fulfillmentChecks.get(p.id) === "verified" : ["committed","completed"].includes(p.status)) ? "completed" : "pending"}"><h2>${p.clearing_mode === "comfort" ? "Adjust" : "Clear"} ${esc(amount(p.amount))}</h2><span class="tag">${esc(statusText(p))}</span><p class="subtle">Proposal <code>${esc(p.id)}</code></p>${changesTable(p.changes)}${comfortTerms(p)}${hashlockDetails(p)}${approve ? `<form data-approve="${esc(p.id)}" data-digest="${esc(p.digest)}"><label class="consent"><input type="checkbox" name="consent" required ${disabled() ? "disabled" : ""}> I approve these exact changes to my test balances.</label><button type="submit" ${disabled() ? "disabled" : ""}>Approve test clearing</button><button type="button" class="secondary" data-decline="${esc(p.id)}" data-digest="${esc(p.digest)}" ${!online || busy ? "disabled" : ""}>Decline proposal</button><p class="subtle">Approval permits these changes. Reserved amounts remain unavailable while a settlement outcome is pending.</p></form>` : !["committed","completed","aborted","rejected","expired"].includes(p.status) ? "<p>Waiting for participants and settlement evidence. Closing this app does not cancel the operation.</p>" : ""}</article>`;
  }

  function comfortTerms(proposal, onlyPeer = null) {
    if (proposal.clearing_mode !== "comfort") return "";
    return `<section class="comfort-terms"><h3>Comfort adjustment · manual approval</h3><p>This proposal aims to improve a shared comfort position. A helping relationship can take on more debt within its agreed limits. Your net position is preserved when the operation completes.</p>${(proposal.changes || []).filter(change => onlyPeer === null || change.peer === onlyPeer).map(change => `<div class="card"><h4>${esc(change.peer)}</h4><p>Distance from shared comfort: <strong>${esc(amount(change.discomfort_before))} → ${esc(amount(change.discomfort_after))}</strong></p><details><summary>Preferences pinned to this proposal</summary><p>Your revision ${esc(change.own_revision)} · peer revision ${esc(change.peer_revision)}</p><p>Shared zone: ${change.shared_comfort && !change.shared_comfort.empty ? `${esc(balanceText(change.shared_comfort.min))} → ${esc(balanceText(change.shared_comfort.max))}` : "No valid shared zone supplied"}</p>${change.own_preferences ? `<p>Your credit grant: ${esc(amount(change.own_preferences.credit_limit))}. Your comfort: ${esc(balanceText(change.own_preferences.comfort_min))} → ${esc(balanceText(change.own_preferences.comfort_max))}. Assistance permission: ${change.own_preferences.auto_adjust ? "yes" : "no"}.</p>` : ""}${change.peer_preferences ? `<p>Peer credit grant: ${esc(amount(change.peer_preferences.credit_limit))}. Peer comfort, from your viewpoint: ${esc(balanceText(-change.peer_preferences.comfort_max))} → ${esc(balanceText(-change.peer_preferences.comfort_min))}. Peer assistance permission: ${change.peer_preferences.auto_adjust ? "yes" : "no"}.</p>` : ""}</details></div>`).join("")}</section>`;
  }

  const contactScales = new Map();
  const preferenceBound = 1000000000000;
  function contactRadius(contact, values) {
    const largest = Math.max(10, Math.abs(contact.balance), ...[values.credit_limit,values.comfort_min,values.comfort_max,contact.peer_preferences?.credit_limit || 0,contact.peer_preferences?.comfort_min || 0,contact.peer_preferences?.comfort_max || 0].map(Number).map(Math.abs));
    const magnitude = Math.pow(10,Math.floor(Math.log10(largest)));
    const fitted = [1,2,5,10].map(factor => factor*magnitude).find(value => value >= largest);
    return Math.min(preferenceBound, Math.max(largest, contactScales.get(contact.peer) || fitted));
  }
  function comfortPreview(contact, values, radius) {
    const peer = contact.peer_preferences;
    const lower = peer ? Math.max(Number(values.comfort_min),-peer.comfort_max,-peer.credit_limit) : 0;
    const upper = peer ? Math.min(Number(values.comfort_max),-peer.comfort_min,Number(values.credit_limit)) : 0;
    const x = value => 500 + Number(value) / radius * 500;
    const overlap = peer && lower <= upper;
    const ownMin = x(values.comfort_min), ownMax = x(values.comfort_max), limit = x(values.credit_limit);
    const signedAmount = value => `${Number(value) < 0 ? "−" : Number(value) > 0 ? "+" : ""}${amount(Math.abs(Number(value)))}`;
    const endpoint = (key, label) => `<div class="diagram-endpoint ${key}" style="--position:${x(values[key])/10}%"><span>${label}</span><output data-value="${key}" aria-label="Your comfort ${key === "comfort_min" ? "minimum" : "maximum"}" aria-live="off">${esc(signedAmount(values[key]))}</output></div>`;
    return `<div class="diagram-drawing"><svg aria-hidden="true" viewBox="0 0 1000 360" preserveAspectRatio="none"><line class="zero-guide" x1="500" y1="5" x2="500" y2="352"/><line class="balance-line" x1="0" y1="244" x2="1000" y2="244"/><rect class="own-comfort-band" x="${ownMin}" y="123" width="${Math.max(2,ownMax-ownMin)}" height="14" rx="7"/><line class="own-connector" x1="${ownMin}" y1="100" x2="${ownMin}" y2="130"/><line class="own-connector" x1="${ownMax}" y1="130" x2="${ownMax}" y2="160"/><line class="own-limit-line" x1="${limit}" y1="20" x2="${limit}" y2="232"/><path class="own-limit-arrow" d="M ${limit-10} 222 L ${limit} 235 L ${limit+10} 222 Z"/>${overlap ? `<rect class="shared-comfort-band" x="${x(lower)}" y="234" width="${Math.max(2,x(upper)-x(lower))}" height="20" rx="10"/>` : ""}${peer ? `<rect class="peer-comfort-band" x="${x(-peer.comfort_max)}" y="313" width="${Math.max(2,x(-peer.comfort_min)-x(-peer.comfort_max))}" height="14" rx="7"/><line class="peer-limit-line" x1="${x(-peer.credit_limit)}" y1="352" x2="${x(-peer.credit_limit)}" y2="260"/><path class="peer-limit-arrow" d="M ${x(-peer.credit_limit)-10} 269 L ${x(-peer.credit_limit)} 256 L ${x(-peer.credit_limit)+10} 269 Z"/>` : ""}</svg>${endpoint("comfort_min","Min")}${endpoint("comfort_max","Max")}<span class="diagram-current" style="left:${x(contact.balance)/10}%" title="Current balance" aria-hidden="true"></span></div><div class="axis-labels" aria-hidden="true"><span>−${esc(amount(radius))}</span><span>0</span><span>+${esc(amount(radius))}</span></div><p class="comfort-preview"><strong>Shared comfort</strong><span>${!peer ? "Waiting for peer preferences" : !overlap ? "No shared comfort zone" : `${esc(signedAmount(lower))} → ${esc(signedAmount(upper))}`}</span><small>Preview · Save to apply your preferences</small></p>`;
  }
  function contactSliders(contact, values, index, locked) {
    const radius = contactRadius(contact,values);
    const control = locked ? "disabled" : "";
    const labels = {credit_limit:"Your maximum",comfort_min:"Your comfort minimum",comfort_max:"Your comfort maximum"};
    return `<div class="preference-axis integrated" data-radius="${radius}"><div class="diagram-heading"><strong>Your comfort zone</strong><span>TEST units</span></div><div class="diagram-key"><span class="own-key">Yours · drag to adjust</span><span class="shared-key">Shared</span><span class="peer-key">Peer · read-only</span></div><div class="integrated-diagram"><div data-comfort-preview>${comfortPreview(contact,values,radius)}</div>${Object.entries(labels).map(([key,label]) => `<input class="diagram-control ${key}" id="contact-${index}-${key}" name="${key}" type="range" min="${key === "credit_limit" ? 0 : -radius}" max="${radius}" step="1" value="${esc(values[key])}" aria-label="${label}" aria-valuetext="${esc(key === "credit_limit" ? amount(values[key]) : balanceText(values[key]))}" ${control}>`).join("")}</div><div class="diagram-values"><label for="contact-${index}-credit_limit">Your credit limit <output data-value="credit_limit">${esc(amount(values.credit_limit))}</output></label><p>Current balance <strong>${esc(balanceText(contact.balance))}</strong></p><p>Peer’s credit limit <strong>${contact.peer_preferences ? esc(amount(contact.peer_preferences.credit_limit)) : "Not received"}</strong></p></div><div class="axis-actions"><button type="button" class="secondary" data-scale="wider" ${radius >= preferenceBound ? "disabled" : ""}>Zoom out ×10</button><button type="button" class="secondary" data-scale="fit">Fit balances and preferences</button><button type="button" class="secondary" data-scale="full">Show full range</button></div><p class="subtle">Drag the Min and Max handles to set your comfort range. The downward arrow sets your credit limit; the upward arrow shows your peer’s limit. Use Tab to select a control and arrow keys to adjust by 1 TEST.</p></div>`;
  }

  function contactHistory(peer) {
    const contact = state.contacts?.find(c => c.peer === peer) || state.balances.find(c => c.peer === peer);
    if (!contact) return intro("Contact unavailable", "This node returned no such direct contact.") + '<a href="#peers">Back to address book</a>';
    const receiptIds = new Set((state.receipts || []).map(r => r.id));
    const entries = [...(state.receipts || []).map(r => ({...r,receipt:true})),...state.proposals.filter(p => !receiptIds.has(p.id))].filter(p => p.changes?.some(c => c.peer === peer));
    entries.sort((a,b) => Number(b.decided_at || b.committed_at || b.created_at || 0)-Number(a.decided_at || a.committed_at || a.created_at || 0));
    return intro(`History with ${peer}`, "Only changes on this contact’s balance are shown. This view uses the latest 100 proposals and 100 receipts returned by your node; it is not a complete ledger or preference-edit history.") + '<a href="#peers">← Back to contact preferences</a>' + (entries.length ? entries.map(entry => {
      const timestamp = entry.decided_at || entry.committed_at || entry.created_at;
      const date = timestamp ? new Date(Number(timestamp)*1000).toLocaleString() : "Time not supplied";
      return `<article class="card"><h2>${esc(statusText(entry))}</h2><p>${esc(date)}</p>${changesTable(entry.changes.filter(c => c.peer === peer))}${comfortTerms(entry,peer)}<details><summary>Local operation ID</summary><code>${esc(entry.id)}</code></details>${entry.receipt ? `<button data-export="${esc(entry.id)}" ${!online || busy ? "disabled" : ""}>Download local receipt</button><p class="subtle">The downloaded receipt contains both of your local edges involved in this operation, including your other peer. The history above shows only this contact.</p>` : "<p>Proposal only; no local receipt was returned.</p>"}</article>`;
    }).join("") : '<p class="empty">No clearing history for this contact in the records returned by your node.</p>');
  }

  function contactCard(contact, index) {
    const own = contact.own;
    const draft = contactDrafts.get(contact.peer);
    const values = draft || own;
    const stale = draft && Number(draft.expected_revision) !== own.revision;
    const locked = !online || busy || Boolean(contact.reserved_by) || stale;
    const peer = contact.peer_preferences;
    const shared = contact.shared_comfort;
    const outside = contact.balance > contact.hard_max || (contact.hard_min !== null && contact.balance < contact.hard_min);
    const control = locked ? "disabled" : "";
    const endpoint = value => value === 0 ? "Neither owes (0 TEST)" : balanceText(value);
    const signedRange = (min, max) => `${endpoint(min)} → ${endpoint(max)}`;
    return `<article class="card contact"><h2>${esc(contact.peer)}</h2><a href="#history/${encodeURIComponent(contact.peer)}">View history with ${esc(contact.peer)}</a><p class="big">${esc(balanceText(contact.balance))}</p>${contact.reserved_by ? "<p class=\"tag\">Pending clearing · preferences locked until outcome</p>" : ""}<p class="subtle">Negative: you owe this peer. Positive: this peer owes you. Zero: neither owes the other.</p><details class="contact-detail-summary"><summary>Saved limits and comfort details</summary><dl class="contact-summary"><dt>Your credit limit for this peer</dt><dd>${esc(amount(own.credit_limit))}</dd><dt>Peer’s credit limit for you</dt><dd>${peer ? esc(amount(peer.credit_limit)) : "Not received yet"}</dd><dt>Current permitted balance range</dt><dd>${contact.hard_min === null ? "Waiting for peer preferences" : esc(signedRange(contact.hard_min, contact.hard_max))}</dd><dt>Peer’s comfort range, from your viewpoint</dt><dd>${peer ? esc(signedRange(-peer.comfort_max, -peer.comfort_min)) : "Not received yet"}</dd><dt>Shared comfort zone · latest received preferences</dt><dd>${!shared ? "Waiting for peer preferences" : shared.empty ? "No shared comfort zone — your ranges do not overlap within the limits." : esc(signedRange(shared.min, shared.max))}</dd></dl></details>${outside ? "<aside>The current balance is outside the newly configured credit limits. Existing debt remains; saving a lower limit does not erase it.</aside>" : ""}<form data-contact="${esc(contact.peer)}" data-revision="${esc(draft?.expected_revision ?? own.revision)}"><h3>Your preferences</h3>${contactSliders(contact,values,index,locked)}<p class="subtle">For example, −5 to 2 means you are comfortable owing up to 5, or being owed up to 2. Your peer independently sets their own limit and comfort range.</p><label class="consent"><input name="auto_adjust" type="checkbox" ${values.auto_adjust ? "checked" : ""} ${control}> Allow this relationship to help comfort clearing</label><p class="subtle">This records your permission for neutral helping moves or increased exposure allowed by the comfort policy. Both peers must allow assistance, and each testnet proposal still requires your manual approval. It does not enable automatic execution.</p>${stale ? "<p role=\"alert\">Preferences changed since you began editing. Reload this contact before saving.</p>" : ""}<button type="submit" ${control}>Save preferences for ${esc(contact.peer)}</button>${draft ? `<button type="button" class="secondary" data-reset-contact="${esc(contact.peer)}">Discard unsaved edits</button>` : ""}<p class="subtle">Revision ${esc(own.revision)}. Saving shares your preferences with this direct peer; it does not change balances.</p></form></article>`;
  }

  function render() {
    const focused = document.activeElement;
    const editingContact = focused?.closest("form[data-contact]")?.dataset.contact;
    const editingField = focused?.name;
    updateConnection();
    document.querySelectorAll("nav a").forEach(a => {
      if (a.hash === `#${page()}` || (page().startsWith("history/") && a.hash === "#peers")) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
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
      peers: () => intro("Your address book", "Set your own credit and comfort preferences for each direct peer. No global graph is shared.") +
        (Array.isArray(state.contacts) ? (state.contacts.length ? state.contacts.map(contactCard).join("") : "<p>No configured contacts yet.</p>") : `<div class="card">${balances.length ? balances.map(b => `<div class="row"><strong>${esc(b.peer)}</strong><span>${esc(balanceText(b.balance))}${b.reserved_by ? `<br><small>Reserved for pending clearing</small>` : ""}</span></div>`).join("") : "<p>No configured test peers yet.</p>"}</div><p>Contact preference editing is unavailable on this node version.</p>`) + "<aside>Peer identities and starting test balances are configured by the network operator. Invitations and ledger imports are not available yet.</aside>",
      clearing: () => intro("Find a loop. Agree the changes.", "Discovery uses neighbour messages. Finding a loop does not approve or settle it.") +
        `<form id="discover" class="card"><h2>Search for test clearing</h2>${comfortAvailable() ? `<fieldset ${disabled() ? "disabled" : ""}><legend>What should this search do?</legend><label><input type="radio" name="mode" value="cancellation" ${searchMode === "cancellation" ? "checked" : ""}> Reduce existing debt</label><label><input type="radio" name="mode" value="comfort" ${searchMode === "comfort" ? "checked" : ""}> Move toward shared comfort</label><p class="subtle">Comfort clearing can use credit in either direction, including agreed zero-balance relationships. Helping moves require bilateral assistance permission. Every proposal still needs manual approval.</p></fieldset>` : ""}<label for="amount">${privateProtocol() ? "Exact amount (whole TEST units)" : "Maximum amount (whole TEST units)"}</label><input id="amount" name="amount" type="number" min="1" max="1000000000" step="1" value="1" required ${disabled() ? "disabled" : ""}><button type="submit" ${disabled() ? "disabled" : ""}>Discover a loop</button>${privateProtocol() ? "<p class=\"subtle\">Search uses this exact amount. If no loop is found, a smaller amount may still clear.</p>" : ""}${state.paused ? "<p>New clearing is paused. Resume in Your node.</p>" : ""}</form>${(state.searches || []).length ? `<div class="card"><h2>Search progress</h2>${state.searches.slice(0,5).map(s => `<p>${esc(s.status === "no_cycle_on_path" ? "No loop found on this path. Other paths may still contain opportunities." : s.status === "cycle_found" ? "Loop found — review participant proposals below." : "Searching — waiting for neighbour messages.")}</p>`).join("")}</div>` : ""}${proposals.length ? proposals.slice().reverse().map(proposalCard).join("") : "<p class=\"empty\">No proposals yet. Discovery may finish without finding a loop.</p>"}`,
      activity: () => intro("Activity and receipts", "A recorded local completion is distinct from approval or an unanswered request.") +
        (receipts.length ? receipts.slice().reverse().map(r => `<article class="card ${(privateProtocol() ? fulfillmentChecks.get(r.id) === "verified" : r.cycle_complete) ? "completed" : "pending"}"><h2>Test receipt</h2><span class="tag">${esc(statusText(r))}</span><p><code>${esc(r.id)}</code></p>${changesTable(r.changes)}${comfortTerms(r)}${hashlockDetails(r)}<button data-export="${esc(r.id)}" ${!online || busy ? "disabled" : ""}>Download receipt JSON</button><p class="subtle">Local testnet journal evidence. Not a bank payment or production settlement certificate.</p></article>`).join("") : "<p class=\"empty\">No receipts returned by your node.</p>") + `<h2>Proposal history</h2>${proposals.length ? proposals.slice().reverse().map(p => `<div class="card"><code>${esc(p.id)}</code><p>${esc(statusText(p))}</p></div>`).join("") : "<p>No proposals recorded.</p>"}`,
      settings: () => intro("Your node. Your permissions.", "The node exchanges messages while your browser is closed.") +
        `<div class="card"><div class="row"><strong>Node identity</strong><span class="node-id">${esc(state.node)}</span></div><div class="row"><strong>Mode / unit</strong><span>TESTNET / TEST</span></div><div class="row"><strong>Protocol</strong><span>${esc(protocolLabel())}</span></div><div class="row"><strong>Approval policy</strong><span>Ask each participant</span></div><button data-action="pause" ${!online || busy ? "disabled" : ""}>${state.paused ? "Resume new clearing" : "Pause new clearing"}</button><p>Pausing stops new work. Already admitted settlement messages still need recovery.</p></div><div class="card"><h2>Connection</h2><p><code>${esc(location.origin)}</code></p><button class="secondary" data-action="refresh" ${busy ? "disabled" : ""}>Refresh node state</button><button class="secondary" data-action="disconnect">Disconnect this browser</button><p class="subtle">Disconnect clears this tab’s token and displayed state. It does not revoke the operator token, stop the node, or cancel pending clearing.</p></div><aside>Test-only shared-secret authentication. The node operator holds the credentials and database. Backups, identity rotation and production key custody require further implementation and review.</aside>`
    };
    let historyPeer = null;
    if (page().startsWith("history/")) { try { historyPeer = decodeURIComponent(page().slice(8)); } catch (_) {} }
    screen.innerHTML = historyPeer !== null ? contactHistory(historyPeer) : (views[page()] || views.overview)();
    if (editingContact && editingField) {
      const form = Array.from(screen.querySelectorAll("form[data-contact]")).find(item => item.dataset.contact === editingContact);
      const field = form?.elements.namedItem(editingField);
      if (field && !field.disabled) field.focus({preventScroll:true});
    }
  }

  async function mutate(path, body, success) {
    if (busy || !online) return;
    busy = true; render();
    try {
      const result = await api(path, body);
      announce(success(result));
      await refresh();
      return true;
    } catch (error) {
      online = false;
      announce(`Request outcome not confirmed: ${error.message} Reconnect and refresh before taking another action.`, true);
      return false;
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
    if (form.dataset.contact) {
      const values = new FormData(form);
      const body = {expected_revision:Number(form.dataset.revision), credit_limit:Number(values.get("credit_limit")), comfort_min:Number(values.get("comfort_min")), comfort_max:Number(values.get("comfort_max")), auto_adjust:values.has("auto_adjust")};
      if (![body.credit_limit,body.comfort_min,body.comfort_max].every(value => Number.isSafeInteger(value) && Math.abs(value) <= 1000000000000) || body.credit_limit < 0 || body.comfort_min > body.comfort_max) {
        announce("Use whole TEST units within ±1,000,000,000,000, a nonnegative credit limit, and a minimum no greater than the maximum.", true); return;
      }
      const peer = form.dataset.contact;
      const saved = await mutate(`/api/contacts/${encodeURIComponent(peer)}/preferences`, body, () => "Preferences saved locally and queued for this peer. Balances are unchanged; every testnet clearing proposal still requires manual approval.");
      if (saved) { contactDrafts.delete(peer); render(); }
      return;
    }
    if (form.id === "discover") {
      const value = Number(new FormData(form).get("amount"));
      if (!Number.isSafeInteger(value) || value <= 0 || value > 1000000000) {
        announce("Enter a positive whole amount up to 1,000,000,000 TEST.", true); return;
      }
      const mode = comfortAvailable() ? new FormData(form).get("mode") || "cancellation" : "cancellation";
      await mutate("/api/discover", {amount: value,...(mode === "comfort" ? {mode} : {})}, r => `Discovery accepted (${r.id}). Waiting for neighbour responses; no balances have been cleared by this request alone.`);
    } else if (form.dataset.approve && new FormData(form).get("consent")) {
      const id = form.dataset.approve;
      await mutate(`/api/proposals/${encodeURIComponent(id)}/approve`, {digest: form.dataset.digest}, () => "The node accepted your approval request. Check the proposal status for settlement progress; approval is not completion.");
    }
  });

  document.addEventListener("input", event => {
    if (event.target.name === "mode" && event.target.closest("#discover")) { searchMode=event.target.value; return; }
    const form = event.target.closest("form[data-contact]");
    if (!form) return;
    if (event.target.name === "comfort_min") event.target.value = Math.min(Number(event.target.value),Number(form.elements.comfort_max.value));
    if (event.target.name === "comfort_max") event.target.value = Math.max(Number(event.target.value),Number(form.elements.comfort_min.value));
    const values = new FormData(form);
    const draft = {expected_revision: Number(form.dataset.revision), credit_limit: values.get("credit_limit"), comfort_min: values.get("comfort_min"), comfort_max: values.get("comfort_max"), auto_adjust: values.has("auto_adjust")};
    contactDrafts.set(form.dataset.contact,draft);
    for (const key of ["credit_limit","comfort_min","comfort_max"]) {
      const text = key === "credit_limit" ? amount(draft[key]) : balanceText(draft[key]);
      if (key === "credit_limit") form.querySelector(`[data-value="${key}"]`).textContent = text;
      form.elements[key].setAttribute("aria-valuetext",text);
    }
    const contact = state.contacts.find(c => c.peer === form.dataset.contact);
    form.querySelector("[data-comfort-preview]").innerHTML = comfortPreview(contact,draft,Number(form.querySelector("[data-radius]").dataset.radius));
    if (!form.querySelector("[data-reset-contact]")) {
      const discard = document.createElement("button"); discard.type="button"; discard.className="secondary";
      discard.dataset.resetContact=form.dataset.contact; discard.textContent="Discard unsaved edits";
      form.querySelector('button[type="submit"]').after(discard);
    }
  });

  document.addEventListener("click", async event => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    if (button.dataset.scale) {
      const form = button.closest("form[data-contact]");
      const contact = state.contacts.find(c => c.peer === form.dataset.contact);
      const current = Number(form.querySelector("[data-radius]").dataset.radius);
      if (button.dataset.scale === "fit") contactScales.delete(contact.peer);
      else contactScales.set(contact.peer,button.dataset.scale === "full" ? preferenceBound : Math.min(preferenceBound,current*10));
      render();
    } else if (button.dataset.resetContact) {
      contactDrafts.delete(button.dataset.resetContact); render(); announce("Unsaved edits discarded; showing the latest preferences received from your node.");
    } else if (button.dataset.action === "disconnect") {
      searchMode="cancellation"; contactDrafts.clear(); sessionGeneration++; token = ""; state = null; online = false; lastSeen = null;
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
        const url = URL.createObjectURL(new Blob([JSON.stringify({mode:"testnet", unit:"TEST", protocol:state.protocol || "legacy-infrastructure", node:state.node, receipt}, null, 2)], {type:"application/json"}));
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
