/* Isolated browser/UI fixture. Real WebAuthn browser operations; mocked HTTP backend.
 * Backend signature/origin/replay checks have separate hosted_auth tests.
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
  const accountBytes = crypto.randomBytes(24).toString('base64url');
  const recovery = Array.from({length:8},() => crypto.randomBytes(16).toString('hex'));
  const terms = {credit_limit:10,comfort_min:-10,comfort_max:10,auto_adjust:true};
  const receipt = {id:crypto.randomBytes(32).toString('hex'),preimage:crypto.randomBytes(32).toString('hex'),
    amount:1,unit:'TEST',protocol:'private-hashlock-v2',status:'committed',local_fulfilled:true,
    clearing_mode:'headroom',policy:'comfort-surplus-bit-v1',direction:1,hashlock_scheme:'sha256-headroom-v1',
    surplus_origin:false,surplus_in:true,surplus_out:false,
    changes:[{peer:'fixture-a',before:0,after:-1,own_preferences:terms,peer_preferences:terms},
             {peer:'fixture-b',before:0,after:1,own_preferences:terms,peer_preferences:terms}]};
  const context = Object.fromEntries(['amount','clearing_mode','direction','id','policy','preimage','protocol','unit'].map(key => [key,receipt[key]]));
  receipt.condition = crypto.createHash('sha256').update(JSON.stringify(context)).digest('hex');
  let signedIn = false, authPosts = [], mutations = [], automatic = false, registrationCount = 0;
  const fixtureState = () => ({node:account.node_id,mode:'testnet',protocol:'private-hashlock-v2',unit:'TEST',
    paused:false,contacts:[],balances:[],proposals:[],receipts:[receipt],searches:[],
    discovery_modes:['cancellation','headroom'],obligation_capable:true,obligations:[],outbox_pending:0,
    automation:{enabled:automatic,next_search_at:0}});
  const server = http.createServer(async (request,response) => {
    const route = new URL(request.url,'http://localhost').pathname;
    const reply = (status,value,headers={}) => {
      const body = JSON.stringify(value); response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store',...headers}); response.end(body);
    };
    const authenticated = signedIn && (request.headers.cookie || '').includes('fixture_session=active');
    if (request.method === 'GET' && route === '/api/session') {
      assert.equal(request.headers.authorization,undefined,'Hosted browser must never transmit an old demo token');
      return authenticated ? reply(200,{account,csrf_token:csrf,hosted:true}) : reply(401,{error:'Sign in required'});
    }
    if (request.method === 'GET' && route === '/api/state') {
      assert.equal(request.headers.authorization,undefined);
      return authenticated ? reply(200,fixtureState()) : reply(401,{error:'Sign in required'});
    }
    if (request.method === 'POST') {
      let raw = ''; for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw);
      if (route.startsWith('/auth/')) authPosts.push({route,body});
      if (route === '/auth/register/begin' || route === '/auth/passkey/begin') {
        if (route.includes('/passkey/')) assert.equal(request.headers['x-csrf-token'],csrf);
        if (body.display_name) account.name = body.display_name;
        return reply(200,{challenge_id:crypto.randomBytes(24).toString('base64url'),public_key:{
          challenge:crypto.randomBytes(32).toString('base64url'),rp:{id:'localhost',name:'LedgerLoops fixture'},
          user:{id:accountBytes,name:account.id,displayName:account.name},
          pubKeyCredParams:[{type:'public-key',alg:-7}],timeout:60000,attestation:'none',
          authenticatorSelection:{residentKey:'required',userVerification:'required'}}});
      }
      if (route === '/auth/register/finish' || route === '/auth/passkey/finish') {
        assert.ok(body.credential.response.attestationObject);
        assert.ok(body.credential.response.clientDataJSON);
        registrationCount++;
        if (route.includes('/passkey/')) return reply(200,{ok:true,account});
        signedIn = true;
        return reply(200,{account,csrf_token:csrf,recovery_codes:recovery},{'Set-Cookie':'fixture_session=active; HttpOnly; SameSite=Lax; Path=/'});
      }
      if (route === '/auth/login/begin') return reply(200,{challenge_id:'login-fixture',public_key:{
        challenge:crypto.randomBytes(32).toString('base64url'),rpId:'localhost',userVerification:'required',timeout:60000}});
      if (route === '/auth/login/finish') {
        assert.ok(body.credential.response.signature);
        assert.equal(body.credential.response.userHandle,accountBytes);
        signedIn = true;
        return reply(200,{account,csrf_token:csrf},{'Set-Cookie':'fixture_session=active; HttpOnly; SameSite=Lax; Path=/'});
      }
      if (route === '/auth/logout') {
        assert.equal(request.headers['x-csrf-token'],csrf); signedIn = false;
        return reply(200,{ok:true},{'Set-Cookie':'fixture_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/'});
      }
      if (route === '/auth/recover') {
        assert.equal(body.account_id,account.id); assert.equal(body.recovery_code,recovery[0]);
        signedIn = true;
        return reply(200,{account,csrf_token:csrf},{'Set-Cookie':'fixture_session=active; HttpOnly; SameSite=Lax; Path=/'});
      }
      assert.ok(authenticated,'API mutation requires the cookie');
      assert.equal(request.headers.authorization,undefined);
      assert.equal(request.headers['x-csrf-token'],csrf,'API mutation requires CSRF');
      mutations.push({route,body});
      if (route === '/api/contacts/invite') return reply(200,{invite_token:'fixture-private-invitation',expires_at:Math.floor(Date.now()/1000)+600});
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
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('WebAuthn.enable');
    await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,
      hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
    await page.goto(origin);
    await page.waitForURL('**/login');
    await page.getByLabel('Your display name').fill('Test person');
    await page.getByLabel('I understand this is TEST data').check();
    await page.getByRole('button',{name:'Create an account with a passkey'}).click();
    await page.getByRole('heading',{name:'Save your account recovery details'}).waitFor();
    assert.equal(await page.locator('#bundle-account').textContent(),account.id);
    assert.equal((await page.locator('#bundle-codes').textContent()).split('\n').length,8);
    assert.equal(await page.getByRole('button',{name:'Continue to my node'}).isDisabled(),true);
    assert.equal(await page.evaluate(() => document.cookie.includes('fixture_session')),false,'Session cookie is HttpOnly');
    await page.getByLabel('I saved my account reference').check();
    await page.getByRole('button',{name:'Continue to my node'}).click();
    await page.getByRole('heading',{name:'Hello, Test person.'}).waitFor();
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
    await page.getByRole('button',{name:'Create an invitation'}).click();
    await page.getByLabel('Invitation code',{exact:true}).waitFor();
    await page.getByLabel('Invitation from your peer').fill('received-fixture-invitation');
    await page.getByRole('button',{name:'Accept invitation'}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Invitation accepted'));
    await page.getByRole('link',{name:'03 / Clearing'}).click();
    await page.getByLabel('Clear within comfort zones',{exact:true}).check();
    await page.getByRole('button',{name:'Discover a loop'}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.includes('Discovery accepted'));
    await page.getByRole('link',{name:'05 / Your node'}).click();
    await page.getByRole('button',{name:'Enable automatic clearing'}).click();
    await page.getByRole('button',{name:'Turn off automatic clearing'}).waitFor();
    await page.getByRole('link',{name:'Passkeys and recovery'}).click();
    await page.getByRole('button',{name:'Add another passkey'}).waitFor();
    await page.getByRole('button',{name:'Add another passkey'}).click();
    await page.waitForFunction(() => document.querySelector('#account-notice').textContent.includes('Another passkey'));
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await page.waitForURL('**/login');
    await page.getByRole('button',{name:'Sign in with a passkey'}).click();
    await page.getByRole('heading',{name:'Hello, Test person.'}).waitFor();
    await page.getByRole('link',{name:'05 / Your node'}).click();
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await page.waitForURL('**/login');
    await page.getByText('Use a recovery code',{exact:true}).click();
    await page.getByLabel('Account reference',{exact:true}).fill(account.id);
    await page.getByLabel('Recovery code',{exact:true}).fill(recovery[0]);
    await page.getByRole('button',{name:'Recover this account'}).click();
    await page.getByRole('heading',{name:'Your account',exact:true}).waitFor();
    assert.equal(await page.locator('#recovery-code').inputValue(),'');
    assert.equal(registrationCount,2);
    assert.ok(mutations.some(r => r.route === '/api/discover' && r.body.mode === 'headroom'));
    assert.ok(mutations.some(r => r.route === '/api/contacts/accept' && r.body.invite_token === 'received-fixture-invitation'));
    assert.ok(mutations.some(r => r.route === '/api/automation' && r.body.enabled === true));
    assert.ok(authPosts.some(r => r.route === '/auth/login/finish'));
    assert.deepEqual(errors,[]);
    console.log('PASS hosted UI: native passkeys, recovery, cookie/CSRF, invitations, headroom receipts and automation');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
