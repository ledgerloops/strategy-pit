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
  const terms = {credit_limit:10,comfort_min:-10,comfort_max:10,auto_adjust:true};
  const receipt = {id:crypto.randomBytes(32).toString('hex'),preimage:crypto.randomBytes(32).toString('hex'),
    amount:1,unit:'TEST',protocol:'private-hashlock-v2',status:'committed',local_fulfilled:true,
    clearing_mode:'headroom',policy:'comfort-surplus-bit-v1',direction:1,hashlock_scheme:'sha256-headroom-v1',
    surplus_origin:false,surplus_in:true,surplus_out:false,
    changes:[{peer:'fixture-a',before:0,after:-1,own_preferences:terms,peer_preferences:terms},
             {peer:'fixture-b',before:0,after:1,own_preferences:terms,peer_preferences:terms}]};
  const context = Object.fromEntries(['amount','clearing_mode','direction','id','policy','preimage','protocol','unit'].map(key => [key,receipt[key]]));
  receipt.condition = crypto.createHash('sha256').update(JSON.stringify(context)).digest('hex');
  const sessions = new Map();
  let authPosts = [], mutations = [], automatic = false, accountCount = 0;
  const fixtureState = () => ({node:account.node_id,mode:'testnet',protocol:'private-hashlock-v2',unit:'TEST',
    paused:false,contacts:[],balances:[],proposals:[],receipts:[receipt],searches:[],
    discovery_modes:['cancellation','headroom'],obligation_capable:true,obligations:[],outbox_pending:0,
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
      return authenticated ? reply(200,{...fixtureState(),node:currentAccount.node_id}) : reply(401,{error:'Sign in required'});
    }
    if (request.method === 'POST') {
      let raw = ''; for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw);
      if (route.startsWith('/auth/')) authPosts.push({route,body});
      if (route === '/api/invitations/preview') return reply(200,{inviter_name:'Test person',peer_name:'Invited friend',expires_at:Math.floor(Date.now()/1000)+600});
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
      if (route === '/api/contacts/invite') return reply(200,{invite_token:'fixture-private-invitation',invite_url:`${origin}/#invite=fixture-private-invitation`,inviter_name:'Test person',peer_name:body.peer_name,expires_at:Math.floor(Date.now()/1000)+600});
      if (route === '/api/contacts/accept') return reply(200,{ok:true});
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
    await page.getByLabel('I understand this is TEST data').check();
    await page.getByRole('button',{name:'Start demo',exact:true}).click();
    await page.getByRole('heading',{name:'Hello, Test person.'}).waitFor();
    assert.equal(await page.evaluate(() => document.cookie.includes('fixture_session')),false,'Identity cookie is HttpOnly');
    const cookie = (await page.context().cookies()).find(item => item.name === 'fixture_session');
    assert.ok(cookie && cookie.httpOnly && cookie.expires > Date.now()/1000,'Demo cookie must persist beyond a browser session');
    await page.goto(origin+'/login');
    await page.waitForURL(origin+'/');
    await page.getByRole('heading',{name:'Hello, Test person.'}).waitFor();
    const reused = await page.evaluate(async () => {
      const response = await fetch('/auth/demo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:'Different name'})});
      return response.json();
    });
    assert.equal(reused.account.id,account.id,'Starting again with the same cookie must keep the account');
    assert.equal(reused.account.name,'Test person');
    assert.equal(accountCount,1);
    assert.equal(await page.getByLabel('Node access token').count(),0,'Hosted view must not show demo-token login');
    await page.getByRole('link',{name:'04 / Activity'}).click();
    await page.getByText('Applied locally · fulfillment verified',{exact:true}).waitFor();
    receipt.surplus_in = false;
    await page.getByRole('link',{name:'05 / Your node'}).click();
    await page.getByRole('button',{name:'Refresh node state'}).click();
    await page.getByRole('link',{name:'04 / Activity'}).click();
    await page.getByText('Verification failed · needs investigation',{exact:true}).waitFor();
    receipt.surplus_in = true;
    await page.getByRole('link',{name:'02 / Peers'}).click();
    await page.getByLabel('Peer name',{exact:true}).fill('Invited friend');
    await page.getByRole('button',{name:'Create an invitation'}).click();
    const inviteLink = page.getByLabel('Invitation link',{exact:true});
    await inviteLink.waitFor();
    const inviteUrl = await inviteLink.inputValue();
    assert.equal(inviteUrl,`${origin}/#invite=fixture-private-invitation`);
    await page.getByLabel('Invitation from your peer').fill(`${origin}/#invite=received-fixture-invitation`);
    await page.getByRole('button',{name:'Accept invitation'}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Invitation accepted'));
    await page.getByRole('link',{name:'03 / Clearing'}).click();
    await page.getByLabel('Clear within comfort zones',{exact:true}).check();
    await page.getByRole('button',{name:'Discover a loop'}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Discovery accepted'));
    await page.getByRole('link',{name:'05 / Your node'}).click();
    await page.getByRole('button',{name:'Enable automatic clearing'}).click();
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
    await fresh.getByLabel('I understand this is TEST data').check();
    await fresh.getByRole('button',{name:'Start demo',exact:true}).click();
    await fresh.getByLabel('Invitation from your peer').waitFor();
    assert.equal(await fresh.getByLabel('Invitation from your peer').inputValue(),'fixture-private-invitation');
    assert.equal(mutations.filter(item => item.route === '/api/contacts/accept').length,acceptsBeforeInvite,'Joining a demo must not accept an invitation automatically');
    await fresh.getByRole('button',{name:'Accept invitation',exact:true}).click();
    await fresh.waitForFunction(() => document.querySelector('#notice').textContent.includes('Invitation accepted'));
    const other = await fresh.evaluate(async () => (await fetch('/api/session')).json());
    assert.notEqual(other.account.id,account.id);
    assert.notEqual(other.account.node_id,account.node_id);
    assert.equal(accountCount,2);
    await freshContext.close();
    assert.ok(mutations.some(r => r.route === '/api/discover' && r.body.mode === 'headroom'));
    assert.ok(mutations.some(r => r.route === '/api/contacts/invite' && r.body.peer_name === 'Invited friend'));
    assert.ok(mutations.some(r => r.route === '/api/contacts/accept' && r.body.invite_token === 'received-fixture-invitation'));
    assert.ok(mutations.some(r => r.route === '/api/contacts/accept' && r.body.invite_token === 'fixture-private-invitation'));
    assert.ok(mutations.some(r => r.route === '/api/automation' && r.body.enabled === true));
    assert.ok(authPosts.every(r => r.route === '/auth/demo/start'),'Demo must not invoke passkey or recovery routes');
    assert.deepEqual(errors,[]);
    console.log('PASS hosted UI: persistent cookie demo identity, same-browser reuse, isolated new identity, CSRF, invitations, headroom receipts and automation');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
