/* Real UI: enter bilateral obligations, obtain consent, then clear their cycle. */
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const directory = process.env.APP_DEMO_DIR;
  if (!directory) throw Error('APP_DEMO_DIR required; start a fresh run_obligations_demo.py');
  const port = Number(process.env.APP_BASE_PORT || 8991);
  const browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
  const pages = {}, errors = [];
  const snapshot = page => page.evaluate(async () => {
    const response = await fetch('/api/state',{headers:{Authorization:`Bearer ${sessionStorage.getItem('ledgerloops.testnet.token')}`},cache:'no-store'});
    if (!response.ok) throw Error('State unavailable');
    return response.json();
  });
  const card = (page,id) => page.locator(`[data-obligation="${id}"]`);
  async function fillProposal(page,peer,direction,value,description) {
    await page.getByRole('link',{name:'06 / Obligations',exact:true}).click();
    await page.getByLabel('Peer',{exact:true}).selectOption(peer);
    await page.getByLabel('Who owes whom?').selectOption(direction);
    await page.getByLabel('Obligation amount').fill(String(value));
    await page.getByLabel('Description (optional)').fill(description);
    await page.getByLabel('I agree to propose this TEST obligation.').check();
  }
  async function propose(page,peer,direction,value,description) {
    await fillProposal(page,peer,direction,value,description);
    const responsePromise = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/obligations'));
    await page.getByRole('button',{name:'Propose obligation',exact:true}).click();
    const response = await responsePromise, result = await response.json();
    assert.equal(response.status(),200,JSON.stringify(result));
    return result.obligation.id;
  }
  async function decide(page,id,approve) {
    await page.getByRole('link',{name:'06 / Obligations',exact:true}).click();
    const item = card(page,id);
    await item.getByText('Needs your approval',{exact:true}).waitFor({timeout:15000});
    if (approve) await item.getByLabel('I agree to this exact TEST obligation and balance change.').check();
    await item.getByRole('button',{name:approve ? 'Approve obligation' : 'Decline obligation',exact:true}).click();
  }
  async function recorded(a,b,id) {
    for (const name of [a,b]) {
      await card(pages[name],id).getByText('Recorded',{exact:true}).waitFor({timeout:15000});
      const item = (await snapshot(pages[name])).obligations.find(o => o.id === id);
      assert.equal(item.status,'committed'); assert.ok(item.applied_at);
    }
  }
  try {
    for (const [i,node] of ['alice','bob','doris'].entries()) {
      const page = await browser.newPage({viewport:{width:390,height:900}});
      page.on('pageerror',error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:${port+i}`);
      const config = JSON.parse(fs.readFileSync(`${directory}/${node}.json`,'utf8'));
      await page.getByLabel('Node access token').fill(config.token);
      await page.getByRole('button',{name:'Connect',exact:true}).click();
      await page.getByRole('heading',{name:`Hello, ${node}.`}).waitFor();
      pages[node] = page;
      assert.ok((await snapshot(page)).balances.every(b => b.balance === 0),'fresh zero-balance fixture required');
    }
    const {alice,bob,doris} = pages;
    const description = '<img src=x onerror="window.unexpectedObligationScript=true"> Shared lunch';
    const first = await propose(alice,'bob','i_owe',3,description);
    await bob.getByRole('link',{name:'06 / Obligations',exact:true}).click();
    await card(bob,first).getByText('Needs your approval',{exact:true}).waitFor();
    assert.equal(await card(bob,first).locator('.obligation-description').textContent(),description);
    assert.equal(await card(bob,first).locator('img').count(),0,'description is text, never HTML');
    assert.ok((await snapshot(alice)).balances.every(b => b.balance === 0),'proposing is not posting');
    assert.ok((await snapshot(bob)).balances.every(b => b.balance === 0),'receiving is not approval');
    assert.equal((await snapshot(bob)).obligations.find(o => o.id === first).direction,'peer_owes');
    await decide(bob,first,true); await recorded('alice','bob',first);
    assert.equal((await snapshot(alice)).balances.find(b => b.peer === 'bob').balance,-3);
    assert.equal((await snapshot(bob)).balances.find(b => b.peer === 'alice').balance,3);

    // Wrong-side excessive exposure is refused without losing the editable form.
    await fillProposal(alice,'bob','i_owe',20,'Too much credit');
    await alice.getByRole('button',{name:'Propose obligation',exact:true}).click();
    await alice.locator('#notice').filter({hasText:'Obligation not accepted'}).waitFor();
    assert.equal(await alice.getByLabel('Obligation amount').inputValue(),'20');
    assert.equal(await alice.locator('#new-obligation button[type=submit]').isDisabled(),false);
    assert.equal((await snapshot(alice)).obligations.length,1);

    const declined = await propose(alice,'bob','peer_owes',1,'Not agreed');
    await decide(bob,declined,false);
    await card(alice,declined).getByText('Not posted',{exact:true}).waitFor();
    assert.equal((await snapshot(alice)).balances.find(b => b.peer === 'bob').balance,-3);
    const second = await propose(bob,'doris','i_owe',3,'Supplies');
    await decide(doris,second,true); await recorded('bob','doris',second);
    const third = await propose(doris,'alice','i_owe',3,'Repair');
    await decide(alice,third,true); await recorded('doris','alice',third);
    await alice.reload();
    await card(alice,first).getByText('Recorded',{exact:true}).waitFor();
    await alice.goto(`http://127.0.0.1:${port}/#history/bob`);
    await card(alice,first).getByText('Recorded',{exact:true}).waitFor();
    await card(alice,declined).getByText('Not posted',{exact:true}).waitFor();

    // The three obligations entered above are the actual balances used for clearing.
    await alice.getByRole('link',{name:'03 / Clearing',exact:true}).click();
    await alice.getByLabel('Exact amount').fill('3');
    await alice.getByRole('button',{name:'Discover a loop',exact:true}).click();
    for (const page of Object.values(pages)) {
      await page.getByRole('link',{name:'03 / Clearing',exact:true}).click();
      await page.getByRole('button',{name:'Approve test clearing',exact:true}).waitFor({timeout:15000});
      await page.locator('input[name=consent]').check();
      await page.getByRole('button',{name:'Approve test clearing',exact:true}).click();
    }
    for (const page of Object.values(pages)) {
      await page.getByRole('link',{name:'04 / Activity',exact:true}).click();
      await page.getByText('Applied locally · fulfillment verified',{exact:true}).first().waitFor({timeout:15000});
      assert.ok((await snapshot(page)).balances.every(b => b.balance === 0),'entered cycle cleared to zero');
    }
    await alice.goto(`http://127.0.0.1:${port}/#history/bob`);
    await card(alice,first).getByText('Recorded',{exact:true}).waitFor();
    await alice.getByRole('heading',{name:'Applied locally · fulfillment verified',exact:true}).waitFor();
    assert.equal(await card(alice,first).count(),1,'contact history keeps obligation alongside clearing');
    for (const width of [320,390,1280]) {
      await alice.setViewportSize({width,height:900});
      await alice.goto(`http://127.0.0.1:${port}/#obligations`);
      assert.equal(await alice.evaluate(() => document.documentElement.scrollWidth > innerWidth),false,`overflow at ${width}px`);
    }
    // A delayed request from a disconnected session must not disable reconnection.
    let releaseRequest;
    const requestBarrier = new Promise(resolve => { releaseRequest = resolve; });
    await alice.route('**/api/obligations',async route => { await requestBarrier; await route.continue(); });
    await fillProposal(alice,'bob','i_owe',1,'Disconnect recovery');
    const oldResponse = alice.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/obligations'));
    await alice.getByRole('button',{name:'Propose obligation',exact:true}).click();
    await alice.getByRole('link',{name:'05 / Your node',exact:true}).click();
    await alice.getByRole('button',{name:'Disconnect this browser',exact:true}).click();
    assert.equal(await alice.getByRole('button',{name:'Connect',exact:true}).isDisabled(),false);
    releaseRequest(); assert.equal((await oldResponse).status(),200);
    await alice.unroute('**/api/obligations');
    const config = JSON.parse(fs.readFileSync(`${directory}/alice.json`,'utf8'));
    await alice.getByLabel('Node access token').fill(config.token);
    await alice.getByRole('button',{name:'Connect',exact:true}).click();
    await alice.getByRole('button',{name:'Disconnect this browser',exact:true}).waitFor();
    await alice.getByRole('link',{name:'06 / Obligations',exact:true}).click();
    await alice.context().setOffline(true);
    await alice.getByRole('button',{name:'Propose obligation',exact:true}).waitFor();
    assert.equal(await alice.getByRole('button',{name:'Propose obligation',exact:true}).isDisabled(),true);
    assert.deepEqual(errors,[]);
    console.log('PASS UI obligation proposal/approval/decline, mirrored balances, limits, safe descriptions, persisted history, entered-obligation cycle clearing, responsive layouts and offline guard');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
