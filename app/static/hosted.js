"use strict";

(() => {
  const notice = document.querySelector("#account-notice");
  const entry = document.querySelector("#account-entry");
  const management = document.querySelector("#account-management");
  let busy = false;
  const invitation = new URLSearchParams(location.hash.slice(1)).get("invite");
  const destination = invitation ? "/#invite=" + encodeURIComponent(invitation) : "/";

  function announce(message, error = false) {
    notice.textContent = message;
    notice.classList.toggle("error", error);
  }

  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),15000);
    try {
      const response = await fetch(path,{method:body === undefined ? "GET" : "POST",
        credentials:"same-origin",cache:"no-store",signal:controller.signal,
        headers:body === undefined ? {} : {"Content-Type":"application/json"},
        ...(body === undefined ? {} : {body:JSON.stringify(body)})});
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(typeof result.error === "string" ? result.error : "The demo service did not accept this request.");
        error.status = response.status; throw error;
      }
      return result;
    } finally { clearTimeout(timeout); }
  }

  async function run(action) {
    if (busy) return;
    busy = true;
    const button = document.querySelector("#start-demo");
    button.disabled = true;
    try { await action(); }
    catch (error) {
      announce(error.name === "AbortError" ? "The request timed out. Try again to check this browser's demo identity." : error.message,true);
    } finally { busy = false; button.disabled = false; }
  }

  document.querySelector("#create-account").addEventListener("submit",event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    run(async () => {
      const result = await api("/auth/demo/start",{display_name:String(data.get("display_name")).trim()});
      if (!result.account?.id) throw new Error("The demo identity response was incomplete. Try again.");
      location.replace(destination);
    });
  });

  async function initialize() {
    if (invitation) {
      try {
        const preview = await api("/api/invitations/preview",{invite_token:invitation});
        const box = document.querySelector("#invitation-preview");
        box.hidden = false;
        document.querySelector("#invitation-title").textContent = `${preview.inviter_name} invited you`;
        document.querySelector("#invitation-description").textContent = "Start your demo to review this invitation. Connecting creates no debt.";
        const name = document.querySelector("#display-name");
        if (!name.value && preview.peer_name) name.value = preview.peer_name;
      } catch (error) { announce(error.message,true); }
    }
    try {
      const session = await api("/api/session");
      if (!session.account?.id) throw new Error("The demo identity response was incomplete.");
      // Migrate older signed-in sessions to the same persistent browser identity.
      await api("/auth/demo/start",{display_name:session.account.name});
      if (new URLSearchParams(location.search).get("manage") === "1") {
        entry.hidden = true; management.hidden = false;
        document.querySelector("#account-name").textContent = session.account.name;
        document.querySelector("#managed-account").textContent = session.account.id;
      } else location.replace(destination);
    } catch (error) {
      entry.hidden = false;
      if (error.status !== 401) announce(error.message,true);
    }
  }
  initialize();
})();
