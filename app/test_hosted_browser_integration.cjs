/* Real Chromium WebAuthn + real Flask + PostgreSQL + real neighbour HTTP delivery.
 * Starts a disposable isolated test server; never touches a user's running demo.
 * Run with LEDGERLOOPS_TEST_POSTGRES_DSN pointing to a local TEST database.
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

async function until(read, predicate, message, timeout=20000) {
  const deadline = Date.now()+timeout;
  while (Date.now() < deadline) {
    const result = await read();
    if (predicate(result)) return result;
    await new Promise(resolve => setTimeout(resolve,150));
  }
  throw new Error(message);
}

(async () => {
  if (!process.env.LEDGERLOOPS_TEST_POSTGRES_DSN) throw new Error('LEDGERLOOPS_TEST_POSTGRES_DSN is required');
  const child = spawn(process.env.PYTHON || 'python',[path.join(__dirname,'run_hosted_test_server.py')],
    {env:process.env,stdio:['ignore','pipe','pipe']});
  const workerErrors = [], serverErrors = [];
  child.stderr.on('data',chunk => serverErrors.push(chunk.toString()));
  let browser;
  try {
    const origin = await new Promise((resolve,reject) => {
      let buffer = '';
      const timer = setTimeout(() => reject(new Error('Hosted browser test server did not start')),20000);
      child.stdout.on('data',chunk => {
        buffer += chunk.toString();
        let end;
        while ((end=buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0,end); buffer = buffer.slice(end+1);
          try {
            const data = JSON.parse(line);
            if (data.worker_error) workerErrors.push(data.worker_error);
            if (data.origin) { clearTimeout(timer); resolve(data.origin); }
          } catch (_) { /* The fixture has no credential-bearing logging. */ }
        }
      });
      child.once('exit',() => { clearTimeout(timer); reject(new Error('Hosted test server exited before startup')); });
    });
    browser = await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium'});
    const pageErrors = [];
    async function pageWithAuthenticator() {
      const context = await browser.newContext();
      const page = await context.newPage();
      page.on('pageerror',error => pageErrors.push(error.message));
      const cdp = await context.newCDPSession(page);
      await cdp.send('WebAuthn.enable');
      const {authenticatorId} = await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',
        hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
      return {page,context,cdp,authenticatorId};
    }
    async function api(user, route, body) {
      return user.page.evaluate(async ({route,body}) => {
        const sessionResponse = await fetch('/api/session',{credentials:'same-origin'});
        if (!sessionResponse.ok) throw new Error(`Session request failed (${sessionResponse.status})`);
        const session = await sessionResponse.json();
        const response = await fetch(route,{method:body === undefined ? 'GET':'POST',credentials:'same-origin',
          headers:body === undefined ? {} : {'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},
          ...(body === undefined ? {} : {body:JSON.stringify(body)})});
        const result = await response.json();
        if (!response.ok) throw new Error(`Request failed (${response.status}): ${result.error || route}`);
        return result;
      },{route,body});
    }
    async function enroll(name) {
      const user = await pageWithAuthenticator();
      await user.page.goto(origin);
      await user.page.waitForURL('**/login');
      await user.page.getByLabel('Your display name').fill(name);
      await user.page.getByLabel('I understand this is TEST data').check();
      await user.page.getByRole('button',{name:'Create an account with a passkey'}).click();
      await user.page.getByRole('heading',{name:'Save your account recovery details'}).waitFor();
      user.recovery = (await user.page.locator('#bundle-codes').textContent()).split('\n');
      assert.equal(user.recovery.length,8);
      await user.page.getByLabel('I saved my account reference').check();
      await user.page.getByRole('button',{name:'Continue to my node'}).click();
      await user.page.getByRole('heading',{name:`Hello, ${name}.`}).waitFor();
      const session = await api(user,'/api/session');
      user.account = session.account;
      const cookie = (await user.context.cookies()).find(item => item.name === '__Host-ledgerloops_session');
      assert.ok(cookie && cookie.secure && cookie.httpOnly && cookie.sameSite === 'Lax');
      assert.equal(await user.page.evaluate(() => document.cookie.includes('__Host-ledgerloops_session')),false);
      assert.equal(await user.page.getByLabel('Node access token').count(),0);
      return user;
    }
    const users = [];
    for (const name of ['Browser Alice','Browser Bob','Browser Carol']) users.push(await enroll(name));
    const [alice,bob,carol] = users;
    async function connect(first,second) {
      await first.page.getByRole('link',{name:'02 / Peers'}).click();
      await first.page.getByRole('button',{name:'Create an invitation'}).click();
      const input = first.page.getByLabel('Invitation code',{exact:true});
      await input.waitFor();
      const invitation = await input.inputValue();
      await second.page.getByRole('link',{name:'02 / Peers'}).click();
      await second.page.getByLabel('Invitation from your peer').fill(invitation);
      await second.page.getByRole('button',{name:'Accept invitation'}).click();
      await until(() => api(second,'/api/state'),state => state.contacts.some(c => c.peer === first.account.node_id), 'Invitation did not establish a peer');
    }
    await connect(alice,bob); await connect(bob,carol); await connect(carol,alice);
    for (const user of users) await until(() => api(user,'/api/state'),state => state.contacts.length === 2 && state.contacts.every(c => c.peer_preferences), 'Peer preferences did not synchronize');

    // Exercise actual autosaving controls on one relationship; set the remaining
    // controls through authenticated HTTP to keep this test focused and quick.
    await alice.page.reload();
    await alice.page.getByRole('heading',{name:'Your address book'}).waitFor();
    const form = alice.page.locator(`form[data-contact="${bob.account.node_id}"]`);
    async function saveControl(selector,action) {
      const saved = alice.page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/preferences') && r.status() === 200);
      await action(form.locator(selector)); await saved;
    }
    await saveControl('input[name=credit_limit]',control => control.press('End'));
    await saveControl('input[name=comfort_min]',control => control.press('Home'));
    await saveControl('input[name=comfort_max]',control => control.press('End'));
    await saveControl('input[name=auto_adjust]',control => control.check());
    const controlled = (await api(alice,'/api/state')).contacts.find(c => c.peer === bob.account.node_id);
    assert.deepEqual(['credit_limit','comfort_min','comfort_max','auto_adjust'].map(key => controlled.own[key]),[10,-10,10,true]);
    for (const user of users) {
      const state = await api(user,'/api/state');
      for (const contact of state.contacts) {
        if (user === alice && contact.peer === bob.account.node_id) continue;
        await api(user,`/api/contacts/${contact.peer}/preferences`,{credit_limit:10,comfort_min:-10,comfort_max:10,
          auto_adjust:true,expected_revision:contact.own.revision});
      }
    }
    for (const user of users) await until(() => api(user,'/api/state'),state => state.contacts.every(c => c.peer_preferences?.auto_adjust), 'Assistance preferences did not synchronize');

    async function obligation(first,second) {
      await first.page.goto(origin+'/#obligations');
      await first.page.locator('#new-obligation').waitFor();
      await first.page.locator('#new-obligation select[name=peer]').selectOption(second.account.node_id);
      await first.page.locator('#new-obligation input[name=amount]').fill('1');
      await first.page.locator('#new-obligation input[name=description]').fill('Browser integration TEST');
      await first.page.locator('#new-obligation input[name=consent]').check();
      await first.page.locator('#new-obligation button[type=submit]').click();
      const pending = await until(() => api(second,'/api/obligations'),items => items.some(item => !item.origin && item.status === 'pending'), 'Obligation proposal did not arrive');
      const proposal = pending.find(item => !item.origin && item.status === 'pending');
      await second.page.goto(origin+'/#obligations');
      const approval = second.page.locator(`form[data-obligation-approve="${proposal.id}"]`);
      await approval.waitFor(); await approval.locator('input[name=consent]').check();
      await approval.getByRole('button',{name:'Approve obligation',exact:true}).click();
      await until(() => api(first,'/api/obligations'),items => items.some(item => item.id === proposal.id && item.status === 'committed'), 'Obligation did not commit');
    }
    await obligation(alice,bob); await obligation(bob,carol);
    let states = await Promise.all(users.map(user => api(user,'/api/state')));
    assert.equal(states.reduce((sum,s) => sum+s.balances.reduce((v,b) => v+Math.abs(b.balance),0),0)/2,2);
    await bob.page.goto(origin+'/#clearing');
    await bob.page.getByLabel('Clear within comfort zones',{exact:true}).check();
    await bob.page.getByRole('button',{name:'Discover a loop'}).click();
    for (const user of users) {
      const state = await until(() => api(user,'/api/state'),s => s.proposals.some(p => p.status === 'pending'), 'Headroom proposal did not arrive');
      const proposal = state.proposals.find(p => p.status === 'pending');
      await user.page.goto(origin+'/#clearing');
      const form = user.page.locator(`form[data-approve="${proposal.id}"]`);
      await form.waitFor(); await form.locator('input[name=consent]').check();
      await form.getByRole('button',{name:'Approve test clearing',exact:true}).click();
    }
    states = [];
    for (const user of users) states.push(await until(() => api(user,'/api/state'),s => s.receipts.some(r => r.status === 'committed') && s.outbox_pending === 0, 'Headroom did not settle'));
    assert.equal(states.reduce((sum,s) => sum+s.balances.reduce((v,b) => v+Math.abs(b.balance),0),0)/2,1);
    assert.equal(states[0].balances.find(b => b.peer === carol.account.node_id).balance,-1);
    assert.ok(states[1].balances.every(b => b.balance === 0));
    assert.equal(states[2].balances.find(b => b.peer === alice.account.node_id).balance,1);
    for (const user of users) {
      await user.page.goto(origin+'/#activity');
      await user.page.locator('span.tag').filter({hasText:'Applied locally · fulfillment verified'}).first().waitFor();
      assert.ok((await api(user,'/api/state')).balances.every(b => b.reserved_by === null));
    }

    await alice.page.goto(origin+'/#settings');
    await alice.page.getByRole('link',{name:'Passkeys and recovery'}).click();
    // A second passkey is a different authenticator. Re-enrolling the same
    // authenticator correctly fails the backend's excludeCredentials check.
    await alice.cdp.send('WebAuthn.removeVirtualAuthenticator',{authenticatorId:alice.authenticatorId});
    await alice.cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',
      hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
    await alice.page.getByRole('button',{name:'Add another passkey'}).click();
    await alice.page.waitForFunction(() => document.querySelector('#account-notice').textContent.includes('Another passkey'));
    await alice.page.getByRole('button',{name:'Sign out',exact:true}).click();
    await alice.page.waitForURL('**/login');
    await alice.page.getByRole('button',{name:'Sign in with a passkey'}).click();
    await alice.page.getByRole('heading',{name:'Hello, Browser Alice.'}).waitFor();
    assert.equal((await api(alice,'/api/session')).account.node_id,alice.account.node_id);
    assert.equal((await api(alice,'/api/state')).balances.find(b => b.peer === carol.account.node_id).balance,-1);
    assert.deepEqual(pageErrors,[]);
    assert.deepEqual(workerErrors,[]);
    console.log('PASS actual hosted browser: real PostgreSQL/passkeys/sessions, invitations, autosave, obligations, HTTP headroom 2→1, receipt verification and stable re-login');
  } finally {
    if (browser) await browser.close();
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null) return resolve();
      const timer = setTimeout(() => { child.kill('SIGKILL'); resolve(); },20000);
      child.once('exit',() => { clearTimeout(timer); resolve(); });
    });
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
