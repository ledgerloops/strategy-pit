/* Authentication recovery against an existing demo; never changes its configs or balances. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const sensitiveValues = [];

(async () => {
  const directory = process.env.APP_DEMO_DIR;
  if (!directory) throw Error('APP_DEMO_DIR required; reuse an existing running demo');
  const port = Number(process.env.APP_BASE_PORT || 8991);
  const config = JSON.parse(fs.readFileSync(path.join(directory,'alice.json')));
  sensitiveValues.push(config.token);
  const configsBefore = ['alice','bob','doris'].map(name => ({
    file:path.join(directory,name+'.json'),contents:fs.readFileSync(path.join(directory,name+'.json'))
  }));
  const browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
  let releaseStale = () => {}, releaseSuccess = () => {};
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror',error => errors.push(error.message));
    await page.addInitScript(() => sessionStorage.setItem('ledgerloops.testnet.token','invalid-cached-test-credential'));
    const staleBarrier = new Promise(resolve => { releaseStale = resolve; });
    let observeStale, staleRequest, first = true;
    const staleObserved = new Promise(resolve => { observeStale = resolve; });
    await page.route('**/api/state',async route => {
      if (!first) return route.continue();
      first = false;
      staleRequest = route.request();
      const response = await route.fetch();
      assert.equal(response.status(),401,'cached invalid credential should be rejected');
      observeStale();
      await staleBarrier;
      await route.fulfill({response});
    });
    await page.goto(`http://127.0.0.1:${port}/`);
    await staleObserved;
    await page.getByLabel('Node access token').fill(config.token);
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.getByRole('heading',{name:'Hello, alice.',exact:true}).waitFor();
    const staleFinished = page.waitForEvent('requestfinished',{predicate:request => request === staleRequest});
    releaseStale();
    await staleFinished;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.getByRole('heading',{name:'Hello, alice.',exact:true}).isVisible(),true,
      'a delayed invalid-token response must not clear a successful new connection');
    assert.equal(await page.evaluate(value => sessionStorage.getItem('ledgerloops.testnet.token') === value,config.token),true,
      'the current credential must survive an older authentication failure');
    await page.unroute('**/api/state');

    await page.getByRole('link',{name:'05 / Your node',exact:true}).click();
    await page.getByRole('button',{name:'Disconnect this browser',exact:true}).click();
    await page.getByLabel('Node access token').fill('invalid-recovery-test-credential');
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#notice').textContent.toLowerCase().includes('config'));
    const guidance = await page.locator('#notice').textContent();
    assert.match(guidance,/token/i,'invalid authentication should identify the credential to use');
    assert.match(guidance,/node/i,'invalid authentication should identify the relevant node');
    assert.equal(await page.getByRole('button',{name:'Connect',exact:true}).isEnabled(),true,
      'authentication rejection must allow another connection attempt');
    await page.getByLabel('Node access token').fill(config.token);
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.getByRole('heading',{name:'Your node. Your permissions.',exact:true}).waitFor();

    const successBarrier = new Promise(resolve => { releaseSuccess = resolve; });
    let observeSuccess, successRequest;
    const successObserved = new Promise(resolve => { observeSuccess = resolve; });
    await page.route('**/api/state',async route => {
      successRequest = route.request();
      const response = await route.fetch();
      assert.equal(response.status(),200,'connected state request should succeed');
      observeSuccess();
      await successBarrier;
      await route.fulfill({response});
    });
    await page.getByRole('button',{name:'Refresh node state',exact:true}).click();
    await successObserved;
    await page.getByRole('button',{name:'Disconnect this browser',exact:true}).click();
    const successFinished = page.waitForEvent('requestfinished',{predicate:request => request === successRequest});
    releaseSuccess();
    await successFinished;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.getByRole('button',{name:'Connect',exact:true}).isVisible(),true,
      'an older successful refresh must not reconnect a disconnected browser');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('ledgerloops.testnet.token') === null),true);
    assert.deepEqual(errors,[]);
    assert.equal(configsBefore.every(before => fs.readFileSync(before.file).equals(before.contents)),true,
      'authentication recovery must preserve every node config byte for byte');
    console.log('PASS delayed authentication failure, valid reconnect, actionable invalid-token recovery and disconnect during refresh; fixture credentials unchanged');
  } finally {
    releaseStale(); releaseSuccess();
    await browser.close();
  }
})().catch(error => {
  let message = String(error.stack || error);
  for (const value of sensitiveValues) if (value) message = message.split(value).join('[redacted]');
  console.error(message); process.exitCode = 1;
});
