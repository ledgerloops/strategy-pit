/* Isolated browser/UI fixture with mocked HTTP backend.
 * Cookie identity and authorization have separate hosted_auth tests.
 * Never connects to a user's demo or hosted account. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {chromium} = require('playwright');

(async () => {
  const root = path.join(__dirname,'static');
  const account = {id:'fixture-account',node_id:'fixture-node',name:'Fixture person'};
  const csrf = crypto.randomBytes(24).toString('base64url');
  const terms = {credit_limit:10,comfort_min:-10,comfort_max:5,auto_adjust:true};
  const receipt = {id:crypto.randomBytes(32).toString('hex'),preimage:crypto.randomBytes(32).toString('hex'),
    amount:1,unit:'TEST',protocol:'private-hashlock-v2',status:'committed',local_fulfilled:true,
    clearing_mode:'headroom',policy:'comfort-surplus-bit-v1',direction:1,hashlock_scheme:'sha256-headroom-v1',
    surplus_origin:false,surplus_in:true,surplus_out:false,
    changes:[{peer:'fixture-a',before:0,after:-1,own_preferences:terms,peer_preferences:terms},
             {peer:'fixture-b',before:0,after:1,own_preferences:terms,peer_preferences:terms}]};
  const context = Object.fromEntries(['amount','clearing_mode','direction','id','policy','preimage','protocol','unit'].map(key => [key,receipt[key]]));
  receipt.condition = crypto.createHash('sha256').update(JSON.stringify(context)).digest('hex');
  const sessions = new Map(), contacts = new Map(), obligations = new Map();
  let authPosts = [], mutations = [], automatic = true, accountCount = 0, failNextObligation = false;
  const fixtureState = current => ({node:account.node_id,mode:'testnet',protocol:'private-hashlock-v2',unit:'TEST',
    paused:false,contacts:contacts.get(current.id) || [],balances:contacts.get(current.id) || [],proposals:[{...receipt,id:'fixture-pending-clearing',status:'pending',approved:false}],receipts:[receipt],searches:[],
    discovery_modes:['cancellation','headroom'],obligation_capable:true,obligations:obligations.get(current.id) || [],outbox_pending:0,
    automation:{enabled:automatic,next_search_at:0}});
  const server = http.createServer(async (request,response) => {
    const route = new URL(request.url,'http://localhost').pathname;
    const reply = (status,value,headers={}) => {
      const body = JSON.stringify(value); response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store',...headers}); response.end(body);
    };
    const cookieToken = /(?:^|; )fixture_session=([^;]+)/.exec(request.headers.cookie || '')?.[1];
    const currentAccount = sessions.get(cookieToken);
    const authenticated = Boolean(currentAccount);
    if (request.method === 'GET' && route === '/api/session') {
      assert.equal(request.headers.authorization,undefined,'Hosted browser must never transmit an old demo token');
      return authenticated ? reply(200,{account:currentAccount,csrf_token:csrf,hosted:true}) : reply(401,{error:'Sign in required'});
    }
    if (request.method === 'GET' && route === '/api/state') {
      assert.equal(request.headers.authorization,undefined);
      return authenticated ? reply(200,{...fixtureState(currentAccount),node:currentAccount.node_id}) : reply(401,{error:'Sign in required'});
    }
    if (request.method === 'POST') {
      let raw = ''; for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw);
      if (route.startsWith('/auth/')) authPosts.push({route,body});
      if (route === '/api/invitations/preview') return reply(200,{inviter_name:'Test person',peer_name:'Invited friend',max_trust:10,expires_at:Math.floor(Date.now()/1000)+600});
      if (route === '/auth/demo/start') {
        if (authenticated) return reply(200,{account:currentAccount,csrf_token:csrf});
        accountCount++;
        const created = accountCount === 1 ? account : {id:`fixture-account-${accountCount}`,node_id:`fixture-node-${accountCount}`};
        created.name = body.display_name;
        const token = crypto.randomBytes(24).toString('base64url');
        sessions.set(token,created);
        return reply(200,{account:created,csrf_token:csrf},{'Set-Cookie':`fixture_session=${token}; Max-Age=2592000; HttpOnly; SameSite=Lax; Path=/`});
      }
      assert.ok(authenticated,'API mutation requires the cookie');
      assert.equal(request.headers.authorization,undefined);
      assert.equal(request.headers['x-csrf-token'],csrf,'API mutation requires CSRF');
      mutations.push({route,body});
      if (route === '/api/contacts/invite') return reply(200,{invite_token:'fixture-private-invitation',invite_url:`${origin}/#invite=fixture-private-invitation`,inviter_name:'Test person',peer_name:body.peer_name,max_trust:body.max_trust,expires_at:Math.floor(Date.now()/1000)+600});
      if (route === '/api/contacts/accept') {
        contacts.set(currentAccount.id,[{peer:'fixture-peer',name:'Invited friend',balance:-2,reserved_by:null,
          own:{...terms,revision:1},peer_preferences:{...terms,revision:1},hard_min:-10,hard_max:10,shared_comfort:{min:-5,max:5,empty:false}}]);
        return reply(200,{ok:true});
      }
      if (route === '/api/obligations') {
        const item = {...body,origin:true,status:'proposed',before:-2,after:-2+(body.direction === 'peer_owes' ? body.amount : -body.amount),digest:'fixture-digest'};
        obligations.set(currentAccount.id,[item,...(obligations.get(currentAccount.id) || [])]);
        if (failNextObligation) { failNextObligation = false; return reply(503,{error:'Accepted by the fixture, but the response was lost'}); }
        return reply(200,{obligation:item});
      }
      if (route === '/api/discover') return reply(200,{id:'fixture-search'});
      if (route === '/api/automation') { automatic = body.enabled; return reply(200,{enabled:automatic}); }
      return reply(404,{error:'Unknown fixture route'});
    }
    const file = {'/':'index.html','/login':'hosted.html','/hosted.js':'hosted.js','/hosted.css':'hosted.css',
      '/style.css':'style.css','/app.js':'app.js','/logo.jpg':'logo.jpg'}[route];
    if (!file) return reply(404,{error:'Unknown fixture asset'});
    let body = fs.readFileSync(path.join(root,file));
    if (route === '/') body = Buffer.from(body.toString().replace('<script src="/app.js" defer></script>',
      '<script>window.LEDGERLOOPS_HOSTED=true;</script><script src="/app.js" defer></script>'));
    response.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'application/javascript','.css':'text/css','.jpg':'image/jpeg'}[path.extname(file)]}); response.end(body);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = `http://localhost:${server.address().port}`;
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium'});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror',error => errors.push(error.message));
    await page.addInitScript(() => sessionStorage.setItem('ledgerloops.testnet.token','old-demo-token-must-stay-local'));
    await page.goto(origin);
    await page.waitForURL('**/login');
    await page.getByLabel('Your display name').waitFor();
    assert.equal(await page.getByRole('heading',{name:'Welcome back',exact:true}).count(),0);
    assert.equal(await page.locator('#recover-account, #recovery-bundle, #sign-in, #add-passkey').count(),0);
    assert.equal(authPosts.length,0,'Opening the demo must not enroll automatically');
    await page.getByLabel('Your display name').fill('Test person');
    await page.getByRole('button',{name:'Continue',exact:true}).click();
    await page.locator('[data-action=invite-peer]').first().waitFor();
    assert.equal(await page.evaluate(() => document.cookie.includes('fixture_session')),false,'Identity cookie is HttpOnly');
    const cookie = (await page.context().cookies()).find(item => item.name === 'fixture_session');
    assert.ok(cookie && cookie.httpOnly && cookie.expires > Date.now()/1000,'Demo cookie must persist beyond a browser session');
    await page.goto(origin+'/login');
    await page.waitForURL(origin+'/');
    await page.locator('[data-action=invite-peer]').first().waitFor();
    const reused = await page.evaluate(async () => {
      const response = await fetch('/auth/demo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:'Different name'})});
      return response.json();
    });
    assert.equal(reused.account.id,account.id,'Starting again with the same cookie must keep the account');
    assert.equal(reused.account.name,'Test person');
    assert.equal(accountCount,1);
    assert.equal(await page.getByLabel('Node access token').count(),0,'Hosted view must not show demo-token login');
    assert.equal(await page.getByRole('navigation',{name:'Main navigation'}).isVisible(),false,'A participant without peers only sees invitations');
    assert.equal(await page.locator('#screen input[type=range], #screen input[type=checkbox]').count(),0);
    assert.equal(await page.getByRole('button',{name:'Discover a loop',exact:true}).count(),0);
    assert.equal(await page.locator('#screen .metrics').count(),0);
    assert.equal(await page.locator('#create-invitation').count(),0,'Inviting is an action, not a permanent form');
    await page.locator('[data-action=invite-peer]').first().click();
    const dialog = page.locator('#hosted-dialog');
    await dialog.waitFor();
    assert.equal(await dialog.evaluate(element => element.open),true,'Inviting opens a native modal');
    const inviteForm = dialog.locator('#create-invitation');
    assert.equal(await inviteForm.locator('[name=max_trust]').inputValue(),'10');
    await inviteForm.locator('[name=peer_name]').fill('Draft peer');
    await inviteForm.locator('[name=max_trust]').fill('14');
    await page.keyboard.press('Escape');
    assert.equal(await dialog.evaluate(element => element.open),false,'Escape closes the modal');
    await page.locator('[data-action=invite-peer]').first().click();
    assert.equal(await dialog.locator('[name=peer_name]').inputValue(),'Draft peer','Invite drafts survive closing');
    assert.equal(await dialog.locator('[name=max_trust]').inputValue(),'14');
    await dialog.locator('[name=peer_name]').fill('Invited friend');
    await dialog.locator('[name=max_trust]').fill('10');
    await dialog.getByRole('button',{name:'Create invite link',exact:true}).click();
    const inviteLink = page.getByLabel('Invitation link',{exact:true});
    await inviteLink.waitFor();
    const inviteUrl = await inviteLink.inputValue();
    assert.equal(inviteUrl,`${origin}/#invite=fixture-private-invitation`);
    await page.keyboard.press('Escape');
    const acceptsBeforeHash = mutations.filter(item => item.route === '/api/contacts/accept').length;
    // Existing participants can open an invite in the same tab without reloading
    // the application. Fragment changes must load the preview and draft token.
    await page.evaluate(() => {
      window.sameDocumentInviteFixture = true;
      location.hash = 'invite=received-fixture-invitation';
    });
    await page.getByRole('heading',{name:'Test person invited you',exact:true}).waitFor();
    assert.equal(await page.evaluate(() => window.sameDocumentInviteFixture),true,'Invite navigation must remain in the existing document');
    assert.equal(await page.locator('#accept-invitation input[name=invite_token]').inputValue(),'received-fixture-invitation');
    assert.equal(mutations.filter(item => item.route === '/api/contacts/accept').length,acceptsBeforeHash,'An existing participant must explicitly accept the invitation');
    await page.getByRole('button',{name:'Accept invitation'}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Invitation accepted'));
    await page.goto(origin+'/#overview');
    const peerCard = page.locator('article[data-peer="fixture-peer"]');
    await peerCard.getByRole('heading',{name:'Invited friend',exact:true}).waitFor();
    assert.equal(await page.locator('#screen input[type=range], #screen input[type=checkbox]').count(),0);
    await peerCard.getByRole('button',{name:'Record a value delivery',exact:true}).click();
    await page.locator('#new-obligation').waitFor();
    assert.equal(await page.locator('#new-obligation [name=peer]').inputValue(),'fixture-peer');
    assert.equal(/obligation/i.test(await dialog.innerText()),false,'Product copy describes value deliveries');
    assert.equal(await page.locator('#new-obligation [name=consent]').count(),0,'The explicit submit button records consent');
    await page.locator('#new-obligation input[name=amount]').fill('3');
    await page.locator('#new-obligation select[name=direction]').selectOption('peer_owes');
    await page.locator('#new-obligation input[name=description]').fill('Shared lunch TEST event');
    assert.match(await page.locator('[data-obligation-preview]').textContent(),/You owe Invited friend 2 TEST → Invited friend owes you 1 TEST/,'The amount changes the current balance rather than replacing it');
    await page.locator('#new-obligation select[name=direction]').selectOption('i_owe');
    assert.match(await page.locator('[data-obligation-preview]').textContent(),/You owe Invited friend 2 TEST → You owe Invited friend 5 TEST/,'Receiving value lowers your balance');
    await page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/state');
    assert.equal(await page.locator('#new-obligation input[name=description]').inputValue(),'Shared lunch TEST event','Background polling preserves an open delivery draft');
    await page.keyboard.press('Escape');
    assert.equal(await dialog.evaluate(element => element.open),false);
    await peerCard.getByRole('button',{name:'Record a value delivery',exact:true}).click();
    assert.equal(await page.locator('#new-obligation input[name=amount]').inputValue(),'3','Delivery drafts survive closing');
    assert.equal(await page.locator('#new-obligation input[name=description]').inputValue(),'Shared lunch TEST event');
    await page.locator('#new-obligation select[name=direction]').selectOption('peer_owes');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true,'Peer view fits a small viewport');
    assert.equal(await dialog.evaluate(element => element.getBoundingClientRect().right <= innerWidth && element.getBoundingClientRect().left >= 0),true,'The modal fits a small viewport');
    await page.getByRole('button',{name:'Send for confirmation',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Waiting for your peer'));
    assert.ok(mutations.some(item => item.route === '/api/obligations' && item.body.peer === 'fixture-peer' && item.body.amount === 3 && item.body.direction === 'peer_owes'));
    await page.waitForFunction(() => !document.querySelector('#hosted-dialog').open);
    // The server can accept a proposal before its response is lost. A later
    // state refresh reconciles the retained request id and removes stale submit
    // controls instead of allowing the same delivery to be entered twice.
    obligations.get(account.id).forEach(item => item.status = 'committed');
    await peerCard.getByRole('button',{name:'Record a value delivery',exact:true}).click();
    await page.locator('#new-obligation input[name=amount]').fill('1');
    await page.locator('#new-obligation input[name=description]').fill('Uncertain delivery response fixture');
    const beforeUncertain = mutations.filter(item => item.route === '/api/obligations').length;
    failNextObligation = true;
    await page.getByRole('button',{name:'Send for confirmation',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('not confirmed'));
    await page.waitForFunction(() => !document.querySelector('#hosted-dialog').open);
    assert.equal(mutations.filter(item => item.route === '/api/obligations').length,beforeUncertain+1,'Accepted requests reconcile without a second submission');
    await page.goto(origin+'/#activity');
    await page.getByText('Applied locally · fulfillment verified',{exact:true}).waitFor();
    receipt.surplus_in = false;
    await page.goto(origin+'/#settings');
    await page.getByRole('button',{name:'Refresh node state'}).click();
    await page.goto(origin+'/#activity');
    await page.getByText('Verification failed · needs investigation',{exact:true}).waitFor();
    receipt.surplus_in = true;
    await page.goto(origin+'/#clearing');
    await page.getByText('Clearing runs automatically in the background.',{exact:false}).first().waitFor();
    assert.equal(await page.locator('#discover, form[data-approve]').count(),0,'Hosted clearing must not ask participants to discover or approve loops');
    assert.equal(await page.getByRole('button',{name:'Discover a loop',exact:true}).count(),0);
    await page.goto(origin+'/#settings');
    await page.getByRole('button',{name:'Turn off automatic clearing'}).waitFor();
    await page.getByRole('link',{name:'Demo identity',exact:true}).click();
    await page.getByRole('heading',{name:'Your account',exact:true}).waitFor();
    assert.equal(await page.locator('#recover-account, #recovery-bundle, #sign-in, #add-passkey, #sign-out').count(),0);
    // Another isolated browser has no identity cookie and starts its own demo.
    const freshContext = await browser.newContext();
    const fresh = await freshContext.newPage();
    fresh.on('pageerror',error => errors.push(error.message));
    const acceptsBeforeInvite = mutations.filter(item => item.route === '/api/contacts/accept').length;
    await fresh.goto(inviteUrl);
    await fresh.waitForURL('**/login#invite=fixture-private-invitation');
    await fresh.getByRole('heading',{name:'Test person invited you',exact:true}).waitFor();
    await fresh.getByLabel('Your display name').waitFor();
    assert.equal(await fresh.getByLabel('Your display name').inputValue(),'Invited friend');
    assert.equal(await fresh.getByRole('heading',{name:'Welcome back',exact:true}).count(),0);
    assert.equal(mutations.filter(item => item.route === '/api/contacts/accept').length,acceptsBeforeInvite,'Preview must not accept an invitation');
    await fresh.getByLabel('Your display name').fill('Another person');
    assert.equal(await fresh.locator('[name=max_trust]').inputValue(),'10');
    assert.match(await fresh.locator('#own-comfort').textContent(),/-10 to \+5 TEST/);
    assert.match(await fresh.locator('#shared-comfort').textContent(),/-5 to \+5 TEST/);
    await fresh.locator('[name=max_trust]').fill('6');
    assert.match(await fresh.locator('#own-comfort').textContent(),/-6 to \+3 TEST/);
    assert.match(await fresh.locator('#shared-comfort').textContent(),/-5 to \+3 TEST/);
    await fresh.getByRole('button',{name:'Connect with Test person',exact:true}).click();
    await fresh.locator('article[data-peer="fixture-peer"]').waitFor();
    assert.equal(mutations.filter(item => item.route === '/api/contacts/accept').length,acceptsBeforeInvite+1,'One explicit connect action enrolls and accepts');
    assert.ok(mutations.some(item => item.route === '/api/contacts/accept' && item.body.invite_token === 'fixture-private-invitation' && item.body.max_trust === 6));
    const other = await fresh.evaluate(async () => (await fetch('/api/session')).json());
    assert.notEqual(other.account.id,account.id);
    assert.notEqual(other.account.node_id,account.node_id);
    assert.equal(accountCount,2);
    await freshContext.close();
    assert.equal(mutations.some(r => r.route === '/api/discover' || /^\/api\/proposals\/[^/]+\/approve$/.test(r.route)),false,'Hosted browser must never initiate discovery or approve clearing');
    assert.ok(mutations.some(r => r.route === '/api/contacts/invite' && r.body.peer_name === 'Invited friend' && r.body.max_trust === 10));
    assert.ok(mutations.some(r => r.route === '/api/contacts/accept' && r.body.invite_token === 'received-fixture-invitation'));
    assert.ok(mutations.some(r => r.route === '/api/contacts/accept' && r.body.invite_token === 'fixture-private-invitation'));
    assert.equal(mutations.some(r => r.route === '/api/automation'),false,'Automatic clearing must already be enabled without participant setup');
    assert.ok(authPosts.every(r => r.route === '/auth/demo/start'),'Demo must not invoke passkey or recovery routes');
    assert.deepEqual(errors,[]);
    console.log('PASS hosted UI: persistent cookie demo identity, same-browser reuse, isolated new identity, CSRF, named invites, value delivery deltas, explicit confirmation, modal drafts, uncertain-response reconciliation and asymmetric trust previews, verified headroom receipts and automatic clearing by default');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
