"use strict";

(() => {
  const notice = document.querySelector("#account-notice");
  const entry = document.querySelector("#account-entry");
  const management = document.querySelector("#account-management");
  const name = document.querySelector("#display-name");
  const maximum = document.querySelector("#maximum-trust");
  const submit = document.querySelector("#start-demo");
  const invitation = new URLSearchParams(location.hash.slice(1)).get("invite");
  let busy = false, preview = null, session = null, ready = false;
  const units = value => `${value.toLocaleString()} TEST`;
  const signed = value => value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString();
  const range = (lower,upper) => `${signed(lower)} to ${signed(upper)} TEST`;

  function announce(message, error = false) {
    notice.textContent = message;
    notice.classList.toggle("error", error);
  }

  async function api(path, body, csrf = "") {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),15000);
    try {
      const response = await fetch(path,{method:body === undefined ? "GET" : "POST",
        credentials:"same-origin",cache:"no-store",signal:controller.signal,
        headers:body === undefined ? {} : {"Content-Type":"application/json",...(csrf ? {"X-CSRF-Token":csrf} : {})},
        ...(body === undefined ? {} : {body:JSON.stringify(body)})});
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(typeof result.error === "string" ? result.error : "The demo service did not accept this request.");
        error.status = response.status; throw error;
      }
      return result;
    } finally { clearTimeout(timeout); }
  }

  function updateTrust() {
    if (!preview) return;
    const selected = Number(maximum.value);
    const valid = maximum.value !== "" && Number.isSafeInteger(selected) && selected >= 0 && selected <= 1000000000;
    maximum.setCustomValidity(valid ? "" : "Choose a whole number from 0 to 1,000,000,000 TEST.");
    const issuer = Number.isSafeInteger(preview.max_trust) ? preview.max_trust : 10;
    document.querySelector("#inviter-trust").textContent = `${preview.inviter_name} chose a maximum trust of ${units(issuer)}.`;
    document.querySelector("#own-comfort").textContent = valid ? `Your comfort zone: ${range(-selected,Math.floor(selected/2))}.` : "Enter your maximum trust to preview the comfort zones.";
    document.querySelector("#shared-comfort").textContent = valid ? `Shared comfort zone: ${range(Math.max(-selected,-Math.floor(issuer/2)),Math.min(Math.floor(selected/2),issuer))}.` : "";
  }
  maximum.addEventListener("input",updateTrust);

  document.querySelector("#create-account").addEventListener("submit",async event => {
    event.preventDefault();
    if (busy || !ready) return;
    const displayName = name.value.trim();
    name.setCustomValidity(displayName ? "" : "Enter your display name.");
    if (!displayName) { name.reportValidity(); return; }
    updateTrust();
    if (invitation && !maximum.reportValidity()) return;
    busy = true; submit.disabled = true;
    try {
      // Identity creation and connecting happen only after this explicit submit.
      // A retry reuses the same cookie identity and invitation acceptance.
      const result = await api("/auth/demo/start",{display_name:displayName});
      if (!result.account?.id) throw new Error("The demo identity response was incomplete. Try again.");
      session = result;
      if (invitation) {
        name.value = session.account.name;
        name.readOnly = true;
        document.querySelector("#existing-identity").hidden = false;
        if (!session.csrf_token) session = await api("/api/session");
        if (!session.csrf_token) throw new Error("The demo session response was incomplete. Try again.");
        await api("/api/contacts/accept",{invite_token:invitation,max_trust:Number(maximum.value)},session.csrf_token);
      }
      location.replace("/");
    } catch (error) {
      announce(error.name === "AbortError" ? "The request timed out. Try again to check this browser's demo identity." : error.message,true);
    } finally { busy = false; submit.disabled = false; }
  });
  name.addEventListener("input",() => name.setCustomValidity(""));

  async function initialize() {
    if (invitation) {
      try {
        preview = await api("/api/invitations/preview",{invite_token:invitation});
        if (typeof preview.inviter_name !== "string") throw new Error("The invitation response was incomplete.");
        document.querySelector("#account-title").textContent = "Connect on LedgerLoops";
        document.querySelector("#invitation-preview").hidden = false;
        document.querySelector("#invitation-trust").hidden = false;
        document.querySelector("#invitation-title").textContent = `${preview.inviter_name} invited you`;
        document.querySelector("#invitation-description").textContent = "Set your name and your own maximum trust to connect.";
        if (preview.peer_name) name.value = preview.peer_name;
        maximum.required = true;
        submit.textContent = `Connect with ${preview.inviter_name}`;
        updateTrust();
      } catch (error) {
        announce(error.message,true);
        // An invalid invitation must not enroll a new identity accidentally.
        return;
      }
    }
    try {
      session = await api("/api/session");
      if (!session.account?.id) throw new Error("The demo identity response was incomplete.");
      if (invitation) {
        name.value = session.account.name;
        name.readOnly = true;
        document.querySelector("#existing-identity").hidden = false;
      } else if (new URLSearchParams(location.search).get("manage") === "1") {
        entry.hidden = true; management.hidden = false;
        document.querySelector("#account-name").textContent = session.account.name;
        document.querySelector("#managed-account").textContent = session.account.id;
        return;
      } else { location.replace("/"); return; }
    } catch (error) {
      if (error.status !== 401) {
        announce(error.message,true);
        return;
      }
    }
    ready = true;
    entry.hidden = false;
  }
  initialize();
})();
