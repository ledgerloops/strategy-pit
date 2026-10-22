/* Real Chromium + real Flask + PostgreSQL + real neighbour HTTP delivery.
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
    const pageErrors = [], manualClearingRequests = [];
    async function demoPage() {
      const context = await browser.newContext();
      const page = await context.newPage();
      page.on('pageerror',error => pageErrors.push(error.message));
      page.on('request',request => {
        const route = new URL(request.url()).pathname;
        if (request.method() === 'POST' && (route === '/api/discover' || route === '/api/proposals/approve' || /^\/api\/proposals\/[^/]+\/approve$/.test(route))) manualClearingRequests.push(route);
      });
      return {page,context};
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
      const user = await demoPage();
      await user.page.goto(origin);
      await user.page.waitForURL('**/login');
      await user.page.getByLabel('Your display name').waitFor();
      assert.equal(await user.page.getByRole('heading',{name:'Welcome back',exact:true}).count(),0);
      assert.equal(await user.page.locator('#recover-account, #recovery-bundle, #sign-in, #add-passkey').count(),0);
      await user.page.getByLabel('Your display name').fill(name);
      await user.page.getByRole('button',{name:'Start demo',exact:true}).click();
      await user.page.getByRole('heading',{name:`Hello, ${name}.`}).waitFor();
      assert.equal(await user.page.getByRole('navigation',{name:'Main navigation'}).isVisible(),false);
      assert.equal(await user.page.locator('#screen input[type=range], #screen input[type=checkbox]').count(),0);
      assert.equal(await user.page.locator('#screen .metrics').count(),0);
      const session = await api(user,'/api/session');
      user.account = session.account;
      const cookie = (await user.context.cookies()).find(item => item.name === '__Host-ledgerloops_session');
      assert.ok(cookie && cookie.secure && cookie.httpOnly && cookie.sameSite === 'Lax' && cookie.expires > Date.now()/1000);
      const reused = await api(user,'/auth/demo/start',{display_name:'Do not replace existing identity'});
      assert.equal(reused.account.id,user.account.id);
      assert.equal(reused.account.name,name);
      assert.equal(await user.page.evaluate(() => document.cookie.includes('__Host-ledgerloops_session')),false);
      assert.equal(await user.page.getByLabel('Node access token').count(),0);
      return user;
    }
    const users = [];
    for (const name of ['Browser Alice','Browser Bob','Browser Carol']) users.push(await enroll(name));
    const [alice,bob,carol] = users;
    async function connect(first,second) {
      await first.page.goto(origin+'/#peers');
      await first.page.getByLabel('Peer name',{exact:true}).fill(second.account.name);
      await first.page.getByRole('button',{name:'Create an invitation'}).click();
      const input = first.page.getByLabel('Invitation link',{exact:true});
      await input.waitFor();
      const invitation = await input.inputValue();
      const url = new URL(invitation);
      assert.equal(url.origin,origin);
      assert.ok(url.hash.startsWith('#invite='));
      await second.page.goto(invitation);
      await second.page.getByRole('heading',{name:`${first.account.name} invited you`,exact:true}).waitFor();
      await second.page.getByRole('button',{name:'Accept invitation'}).click();
      await until(() => api(second,'/api/state'),state => state.contacts.some(c => c.peer === first.account.node_id), 'Invitation did not establish a peer');
      // The server can expose the relationship before the accepting tab has
      // finished its POST response, redirect and refresh. Let that UI action
      // finish before the same tab creates its next invitation.
      await second.page.waitForURL(origin+'/#overview');
      await second.page.waitForFunction(() => {
        const button = document.querySelector('button[data-record-event]');
        return button && !button.disabled;
      });
    }
    await connect(alice,bob); await connect(bob,carol); await connect(carol,alice);
    for (const user of users) {
      const state = await until(() => api(user,'/api/state'),state => state.contacts.length === 2 && state.contacts.every(c => c.peer_preferences), 'Peer preferences did not synchronize');
      assert.equal(state.automation.enabled,true,'Background clearing must be enabled without participant setup');
      assert.ok(state.contacts.every(contact => contact.own.auto_adjust && contact.peer_preferences.auto_adjust),'New hosted peers must allow automatic clearing by default');
    }

    // Exercise actual autosaving controls on one relationship; set the remaining
    // controls through authenticated HTTP to keep this test focused and quick.
    const initialAliceContact = (await api(alice,'/api/state')).contacts.find(contact => contact.peer === bob.account.node_id);
    await api(alice,`/api/contacts/${bob.account.node_id}/preferences`,{credit_limit:0,comfort_min:0,comfort_max:0,auto_adjust:false,expected_revision:initialAliceContact.own.revision});
    const initialBobContact = (await api(bob,'/api/state')).contacts.find(contact => contact.peer === alice.account.node_id);
    await api(bob,`/api/contacts/${alice.account.node_id}/preferences`,{credit_limit:0,comfort_min:0,comfort_max:0,auto_adjust:false,expected_revision:initialBobContact.own.revision});
    await until(() => api(alice,'/api/state'),state => state.contacts.find(contact => contact.peer === bob.account.node_id).peer_preferences?.credit_limit === 0,'Deterministic slider fixture preferences did not synchronize');
    await alice.page.goto(origin+'/#preferences');
    await alice.page.reload();
    await alice.page.locator(`form[data-contact="${bob.account.node_id}"]`).waitFor();
    const form = alice.page.locator(`form[data-contact="${bob.account.node_id}"]`);
    async function saveControl(selector,action) {
      const saved = alice.page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/preferences') && r.status() === 200);
      try { await action(form.locator(selector)); await saved; }
      catch (error) { throw new Error(`Autosave ${selector}: ${error.message}`); }
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

    async function economicEvent(first,second,direction='i_owe',amount=1,verifyBalance=true) {
      const before = (await api(first,'/api/state')).contacts.find(contact => contact.peer === second.account.node_id).balance;
      await first.page.goto(origin+'/#overview');
      const card = first.page.locator(`article[data-peer="${second.account.node_id}"]`);
      await card.getByRole('heading',{name:second.account.name,exact:true}).waitFor();
      assert.equal(await first.page.locator('#screen input[type=range], #screen input[type=checkbox]').count(),0);
      await card.getByRole('button',{name:'Record an economic event',exact:true}).click();
      await first.page.locator('#new-obligation').waitFor();
      assert.equal(await first.page.locator('#new-obligation [name=peer]').inputValue(),second.account.node_id);
      await first.page.locator('#new-obligation select[name=direction]').selectOption(direction);
      assert.equal(/obligation/i.test(await first.page.locator('#screen').innerText()),false);
      await first.page.locator('#new-obligation input[name=amount]').fill(String(amount));
      await first.page.locator('#new-obligation input[name=description]').fill('Browser integration TEST');
      await first.page.getByRole('button',{name:'Record event',exact:true}).click();
      assert.equal((await api(first,'/api/obligations')).filter(item => item.status !== 'committed').length,0,'Recording requires explicit consent');
      await first.page.locator('#new-obligation input[name=consent]').check();
      await first.page.locator('#new-obligation button[type=submit]').click();
      const pending = await until(() => api(second,'/api/obligations'),items => items.some(item => !item.origin && item.status === 'pending'), 'Obligation proposal did not arrive');
      const proposal = pending.find(item => !item.origin && item.status === 'pending');
      await second.page.goto(origin+'/#overview');
      const approval = second.page.locator(`form[data-obligation-approve="${proposal.id}"]`);
      await approval.waitFor(); await approval.locator('input[name=consent]').check();
      await approval.getByRole('button',{name:'Confirm event',exact:true}).click();
      await until(() => api(first,'/api/obligations'),items => items.some(item => item.id === proposal.id && item.status === 'committed'), 'Economic event did not commit');
      const after = await until(() => api(first,'/api/state'),state => state.contacts.find(contact => contact.peer === second.account.node_id).reserved_by === null,'Event balance did not unlock');
      if (verifyBalance) assert.equal(after.contacts.find(contact => contact.peer === second.account.node_id).balance,before+(direction === 'i_owe' ? -amount : amount),'An economic event adds a delta to the existing balance');
      await until(() => api(second,'/api/state'),state => state.contacts.find(contact => contact.peer === first.account.node_id).reserved_by === null,'Peer event balance did not unlock');
    }
    await economicEvent(alice,bob,'i_owe',2);
    await economicEvent(alice,bob,'peer_owes',1);
    // The second nonzero link creates the improving path. Once both peers
    // confirm its event the background worker may clear before this tab polls.
    await economicEvent(carol,bob,'peer_owes',1,false);
    for (const user of users) {
      await user.page.goto(origin+'/#clearing');
      await user.page.getByText('Clearing runs automatically in the background.',{exact:false}).first().waitFor();
      assert.equal(await user.page.locator('#discover, form[data-approve]').count(),0);
    }
    const states = [];
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
    await alice.page.getByRole('link',{name:'Demo identity',exact:true}).click();
    await alice.page.getByRole('heading',{name:'Your account',exact:true}).waitFor();
    assert.equal(await alice.page.locator('#add-passkey, #sign-out, #recovery-bundle').count(),0);
    await alice.page.goto(origin+'/login');
    await alice.page.waitForURL(origin+'/');
    await alice.page.getByRole('heading',{name:'Hello, Browser Alice.'}).waitFor();
    assert.equal((await api(alice,'/api/session')).account.node_id,alice.account.node_id);
    assert.equal((await api(alice,'/api/state')).balances.find(b => b.peer === carol.account.node_id).balance,-1);
    const secondTab = await alice.context.newPage();
    await secondTab.goto(origin+'/login');
    await secondTab.waitForURL(origin+'/');
    await secondTab.getByRole('heading',{name:'Hello, Browser Alice.'}).waitFor();
    await secondTab.close();
    // Restore the browser's persistent cookies in another isolated session.
    const reopened = await browser.newContext({storageState:await alice.context.storageState()});
    const reopenedPage = await reopened.newPage();
    await reopenedPage.goto(origin+'/login');
    await reopenedPage.waitForURL(origin+'/');
    await reopenedPage.getByRole('heading',{name:'Hello, Browser Alice.'}).waitFor();
    const reopenedSession = await reopenedPage.evaluate(async () => (await fetch('/api/session')).json());
    assert.equal(reopenedSession.account.id,alice.account.id);
    await reopened.close();
    await alice.page.goto(origin+'/#peers');
    await alice.page.getByLabel('Peer name',{exact:true}).fill('Browser Dana');
    await alice.page.getByRole('button',{name:'Create an invitation',exact:true}).click();
    const newInvite = await alice.page.getByLabel('Invitation link',{exact:true}).inputValue();
    const newcomer = await demoPage();
    const acceptRequests = [];
    newcomer.page.on('request',request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/contacts/accept') acceptRequests.push(request);
    });
    await newcomer.page.goto(newInvite);
    await newcomer.page.getByRole('heading',{name:'Browser Alice invited you',exact:true}).waitFor();
    await newcomer.page.getByLabel('Your display name').waitFor();
    assert.equal(await newcomer.page.getByLabel('Your display name').inputValue(),'Browser Dana');
    assert.equal(await newcomer.page.getByRole('heading',{name:'Welcome back',exact:true}).count(),0);
    assert.equal(acceptRequests.length,0,'Preview must not accept the invitation');
    await newcomer.page.getByRole('button',{name:'Start demo',exact:true}).click();
    await newcomer.page.locator('#accept-invitation').waitFor();
    assert.equal((await api(newcomer,'/api/state')).contacts.length,0,'Joining must not silently connect peers');
    assert.equal(acceptRequests.length,0,'Demo enrollment must not accept the invitation');
    await newcomer.page.getByRole('button',{name:'Accept invitation',exact:true}).click();
    await until(() => api(newcomer,'/api/state'),state => state.contacts.some(contact => contact.peer === alice.account.node_id),'Named invite did not connect the new demo identity');
    assert.equal(acceptRequests.length,1);
    await newcomer.context.close();
    assert.deepEqual(manualClearingRequests,[],'Clearing must settle without discovery or approval calls from the browser');
    assert.deepEqual(pageErrors,[]);
    assert.deepEqual(workerErrors,[]);
    console.log('PASS actual hosted browser: real PostgreSQL/persistent cookie identity, named invites, autosave, economic event deltas and consent, automatic HTTP headroom 2→1 without participant discovery or approval, receipt verification and stable browser identity');
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
