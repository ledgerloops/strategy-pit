"use strict";

(() => {
  const notice = document.querySelector("#account-notice");
  let busy = false, csrfToken = "", recoveryBundle = null;
  const entry = document.querySelector("#account-entry");
  const management = document.querySelector("#account-management");
  const bundle = document.querySelector("#recovery-bundle");

  function announce(message, error = false) {
    notice.textContent = message;
    notice.classList.toggle("error", error);
  }

  function decode(value) {
    const base64 = value.replace(/-/g,"+").replace(/_/g,"/");
    return Uint8Array.from(atob(base64 + "=".repeat((4-base64.length%4)%4)),c => c.charCodeAt(0));
  }

  function encode(buffer) {
    if (buffer === null || buffer === undefined) return null;
    let binary = "";
    for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
  }

  function options(value) {
    const result = {...value,challenge:decode(value.challenge)};
    if (value.user) result.user = {...value.user,id:decode(value.user.id)};
    for (const key of ["allowCredentials","excludeCredentials"]) {
      if (value[key]) result[key] = value[key].map(item => ({...item,id:decode(item.id)}));
    }
    return result;
  }

  function credentialJSON(credential) {
    if (!credential) throw new Error("Passkey operation was cancelled. No sign-in was completed.");
    const response = {clientDataJSON:encode(credential.response.clientDataJSON)};
    for (const key of ["attestationObject","authenticatorData","signature","userHandle"]) {
      if (key in credential.response) response[key] = encode(credential.response[key]);
    }
    if (typeof credential.response.getTransports === "function") response.transports = credential.response.getTransports();
    return {id:credential.id,rawId:encode(credential.rawId),type:credential.type,
      response,authenticatorAttachment:credential.authenticatorAttachment,
      clientExtensionResults:credential.getClientExtensionResults()};
  }

  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),15000);
    try {
      const response = await fetch(path,{method:body === undefined ? "GET" : "POST",
        credentials:"same-origin",cache:"no-store",signal:controller.signal,
        headers:body === undefined ? {} : {"Content-Type":"application/json",...(csrfToken ? {"X-CSRF-Token":csrfToken} : {})},
        ...(body === undefined ? {} : {body:JSON.stringify(body)})});
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(typeof result.error === "string" ? result.error : "The account service did not accept this request.");
        error.status = response.status; throw error;
      }
      return result;
    } finally { clearTimeout(timeout); }
  }

  function showAccount(account) {
    entry.hidden = true; management.hidden = false;
    document.querySelector("#account-name").textContent = account.name || "Your account";
    document.querySelector("#managed-account").textContent = account.id;
  }

  function authenticated(result, recovered = false) {
    if (!result.account?.id || typeof result.csrf_token !== "string") throw new Error("Sign-in response incomplete. Retry signing in to confirm your account.");
    csrfToken = result.csrf_token;
    if (Array.isArray(result.recovery_codes) && result.recovery_codes.length) {
      recoveryBundle = {account_id:result.account.id,recovery_codes:result.recovery_codes};
      entry.hidden = true; management.hidden = true; bundle.hidden = false;
      document.querySelector("#bundle-account").textContent = result.account.id;
      document.querySelector("#bundle-codes").textContent = result.recovery_codes.join("\n");
      announce("Account created. Save your recovery details before continuing.");
    } else if (recovered) {
      showAccount(result.account);
      announce("Account recovered. Add a passkey before leaving this session if you no longer have access to your existing passkeys.");
    } else location.replace("/");
  }

  async function passkey(kind, data = {}) {
    if (!window.isSecureContext || !window.PublicKeyCredential || !navigator.credentials) {
      throw new Error("Passkeys require a supported browser on this site's HTTPS address. You can still use an existing recovery code.");
    }
    const start = await api(`/auth/${kind}/begin`,data);
    const credential = kind === "login"
      ? await navigator.credentials.get({publicKey:options(start.public_key)})
      : await navigator.credentials.create({publicKey:options(start.public_key)});
    return api(`/auth/${kind}/finish`,{challenge_id:start.challenge_id,credential:credentialJSON(credential)});
  }

  async function run(action) {
    if (busy) return;
    busy = true;
    const buttons = [...document.querySelectorAll("button")];
    const disabled = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    try { await action(); }
    catch (error) {
      announce(error.name === "NotAllowedError" ? "The passkey request was cancelled or timed out. You can try again." : error.name === "AbortError" ? "The request timed out. Try signing in to check whether your account operation completed." : error.message,true);
    } finally {
      busy = false; buttons.forEach((button,index) => { button.disabled = disabled[index]; });
      document.querySelector("#continue-after-recovery").disabled = !document.querySelector("#recovery-saved").checked;
    }
  }

  document.querySelector("#create-account").addEventListener("submit",event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (!data.has("disclosure")) return;
    run(async () => authenticated(await passkey("register",{display_name:String(data.get("display_name")).trim()})));
  });
  document.querySelector("#sign-in").addEventListener("submit",event => {
    event.preventDefault(); run(async () => authenticated(await passkey("login")));
  });
  document.querySelector("#recover-account").addEventListener("submit",event => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    run(async () => {
      const result = await api("/auth/recover",{account_id:String(data.get("account_id")).trim(),recovery_code:String(data.get("recovery_code")).trim()});
      document.querySelector("#recovery-code").value = "";
      authenticated(result,true);
    });
  });
  document.querySelector("#add-passkey").addEventListener("click",() => run(async () => {
    await passkey("passkey"); announce("Another passkey is now registered to this same account.");
  }));
  document.querySelector("#sign-out").addEventListener("click",() => run(async () => {
    await api("/auth/logout",{}); location.replace("/login");
  }));
  document.querySelector("#recovery-saved").addEventListener("change",event => {
    document.querySelector("#continue-after-recovery").disabled = !event.target.checked || busy;
  });
  document.querySelector("#continue-after-recovery").addEventListener("click",() => {
    if (document.querySelector("#recovery-saved").checked) location.assign("/");
  });
  document.querySelector("#download-recovery").addEventListener("click",() => {
    if (!recoveryBundle) return;
    const contents = `LedgerLoops TEST alpha — private account recovery\nSite: ${location.origin}\nAccount reference: ${recoveryBundle.account_id}\n\nEach code works once. Keep this file private.\n\n${recoveryBundle.recovery_codes.join("\n")}\n`;
    const url = URL.createObjectURL(new Blob([contents],{type:"text/plain"}));
    const link = document.createElement("a"); link.href = url; link.download = "ledgerloops-recovery.txt"; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  });

  if (new URLSearchParams(location.search).get("manage") === "1") {
    run(async () => {
      const session = await api("/api/session");
      csrfToken = session.csrf_token; showAccount(session.account);
    });
  }
})();
