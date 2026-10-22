/* Isolated onboarding fixture. Never reads a user's browser or demo data. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

(async () => {
  const sessions = new Map(), posts = [], errors = [];
  let nextAccount = 0, failNextAccept = false;
  const server = http.createServer(async (request,response) => {
    const route = new URL(request.url,'http://localhost').pathname;
    const reply = (status,value,headers={}) => {
      response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store',...headers});
      response.end(JSON.stringify(value));
    };
    const token = /(?:^|; )fixture_identity=([^;]+)/.exec(request.headers.cookie || '')?.[1];
    const session = sessions.get(token);
    if (request.method === 'GET' && route === '/api/session') return session ? reply(200,session) : reply(401,{error:'Sign in required'});
    if (request.method === 'POST') {
      let raw = ''; for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw);
      posts.push({route,body,account:session?.account.id});
      if (route === '/api/invitations/preview') return body.invite_token === 'expired' ? reply(400,{error:'This invitation has expired.'}) : reply(200,{inviter_name:'Alice',peer_name:'Bob',max_trust:12});
      if (route === '/auth/demo/start') {
        if (session) return reply(200,session);
        const id = `fixture-${++nextAccount}`;
        const created = {account:{id,node_id:id,name:body.display_name},csrf_token:`csrf-${id}`};
        sessions.set(id,created);
        return reply(200,created,{'Set-Cookie':`fixture_identity=${id}; Path=/; HttpOnly; SameSite=Lax`});
      }
      if (route === '/api/contacts/accept') {
        assert.ok(session,'Invitation acceptance requires a browser identity');
        assert.equal(request.headers['x-csrf-token'],session.csrf_token,'Acceptance requires the current session CSRF token');
        assert.ok(Number.isSafeInteger(body.max_trust) && body.max_trust >= 0 && body.max_trust <= 1000000000);
        if (failNextAccept) { failNextAccept = false; return reply(503,{error:'Temporary fixture outage. Retry.'}); }
        return reply(200,{ok:true});
      }
      return reply(404,{error:'Unknown fixture route'});
    }
    if (route === '/') { response.writeHead(200,{'Content-Type':'text/html'}); return response.end('<h1>Connected fixture</h1>'); }
    const asset = {'/login':'hosted.html','/hosted.js':'hosted.js','/hosted.css':'hosted.css','/style.css':'style.css','/logo.jpg':'logo.jpg'}[route];
    if (!asset) return reply(404,{error:'Unknown fixture asset'});
    response.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'application/javascript','.css':'text/css','.jpg':'image/jpeg'}[path.extname(asset)]});
    response.end(fs.readFileSync(path.join(__dirname,'static',asset)));
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = `http://localhost:${server.address().port}`;
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium'});
  async function freshPage() {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on('pageerror',error => errors.push(error.message));
    return {page,context};
  }
  try {
    const plain = await freshPage();
    await plain.page.goto(origin+'/login');
    await plain.page.getByLabel('Your display name').waitFor();
    assert.equal(await plain.page.locator('#invitation-trust').isVisible(),false);
    assert.equal(await plain.page.locator('#account-management').isVisible(),false);
    assert.equal(posts.length,0,'Viewing onboarding must not create an account');
    await plain.page.getByLabel('Your display name').fill('Carol');
    await plain.page.getByRole('button',{name:'Continue',exact:true}).click();
    await plain.page.getByRole('heading',{name:'Connected fixture'}).waitFor();
    assert.equal(nextAccount,1);
    assert.equal(posts.filter(post => post.route === '/api/contacts/accept').length,0);
    const writesBeforeManage = posts.filter(post => post.route === '/auth/demo/start').length;
    await plain.page.goto(origin+'/login?manage=1');
    await plain.page.getByRole('heading',{name:'Your account',exact:true}).waitFor();
    assert.equal(posts.filter(post => post.route === '/auth/demo/start').length,writesBeforeManage,'Viewing an existing identity must not mutate it');

    const invited = await freshPage();
    await invited.page.goto(origin+'/login#invite=private-fixture');
    await invited.page.getByRole('heading',{name:'Alice invited you',exact:true}).waitFor();
    await invited.page.getByLabel('Your display name').waitFor();
    assert.equal(await invited.page.getByLabel('Your display name').inputValue(),'Bob');
    const max = invited.page.getByLabel('Your maximum trust');
    assert.equal(await max.inputValue(),'10');
    assert.match(await invited.page.locator('#inviter-trust').textContent(),/Alice.*12 TEST/);
    assert.match(await invited.page.locator('#own-comfort').textContent(),/-10 to \+5 TEST/);
    assert.match(await invited.page.locator('#shared-comfort').textContent(),/-6 to \+5 TEST/);
    assert.equal(nextAccount,1,'Preview must not enroll or connect');
    await max.fill('5');
    assert.match(await invited.page.locator('#own-comfort').textContent(),/-5 to \+2 TEST/,'Odd maximum trust uses a whole TEST comfort bound');
    assert.match(await invited.page.locator('#shared-comfort').textContent(),/-5 to \+2 TEST/);
    await max.fill('2.5');
    await invited.page.getByRole('button',{name:'Connect with Alice',exact:true}).click();
    assert.equal(nextAccount,1,'Invalid maximum trust must not create an identity');
    await max.fill('20');
    assert.match(await invited.page.locator('#shared-comfort').textContent(),/-6 to \+10 TEST/);
    await invited.page.getByLabel('Your display name').fill('Robert');
    failNextAccept = true;
    await invited.page.getByRole('button',{name:'Connect with Alice',exact:true}).click();
    await invited.page.getByText('Temporary fixture outage. Retry.',{exact:true}).waitFor();
    assert.equal(nextAccount,2);
    assert.equal(await invited.page.getByLabel('Your display name').getAttribute('readonly'),'','A created cookie identity must remain visible when connecting needs a retry');
    await invited.page.getByRole('button',{name:'Connect with Alice',exact:true}).click();
    await invited.page.getByRole('heading',{name:'Connected fixture'}).waitFor();
    assert.equal(nextAccount,2,'Retry must reuse the cookie identity');
    const accepted = posts.filter(post => post.route === '/api/contacts/accept');
    assert.equal(accepted.length,2);
    assert.ok(accepted.every(post => post.body.invite_token === 'private-fixture' && post.body.max_trust === 20 && post.account === 'fixture-2'));
    assert.equal(sessions.get('fixture-2').account.name,'Robert');

    // Existing participants explicitly connect under their original cookie identity.
    const beforeExistingView = posts.length;
    await invited.page.goto(origin+'/login#invite=another-private-fixture');
    await invited.page.getByRole('button',{name:'Connect with Alice',exact:true}).waitFor();
    assert.equal(await invited.page.getByLabel('Your display name').inputValue(),'Robert');
    assert.equal(await invited.page.getByLabel('Your display name').getAttribute('readonly'),'');
    assert.equal(posts.slice(beforeExistingView).filter(post => post.route !== '/api/invitations/preview').length,0);
    await invited.page.getByRole('button',{name:'Connect with Alice',exact:true}).click();
    await invited.page.getByRole('heading',{name:'Connected fixture'}).waitFor();
    assert.equal(nextAccount,2);
    assert.equal(posts.filter(post => post.route === '/api/contacts/accept').at(-1).body.max_trust,10);

    const expired = await freshPage();
    await expired.page.goto(origin+'/login#invite=expired');
    await expired.page.getByText('This invitation has expired.',{exact:true}).waitFor();
    assert.equal(await expired.page.locator('#account-entry').isVisible(),false);
    assert.equal(nextAccount,2);
    assert.deepEqual(errors,[]);
    console.log('PASS hosted onboarding: name-only Continue, invitation names/MAX/comfort preview, one explicit connect with CSRF, whole TEST validation, cookie reuse on retry, existing identity preservation and no writes on view');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
