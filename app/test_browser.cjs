/* Requires Playwright and Chromium. Run against a fresh local demo only.
   APP_DEMO_DIR=/tmp/ledgerloops-demo node app/test_browser.cjs */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const dir = process.env.APP_DEMO_DIR;
  if (!dir) throw new Error('Set APP_DEMO_DIR to a fresh local test-network directory');
  const basePort = Number(process.env.APP_BASE_PORT || 8761);
  const privateProtocol = process.env.APP_PROTOCOL === 'private-hashlock-v2';
  const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
  try {
    const pages = {}, errors = [];
    for (const [index,node] of ['alice','bob','doris'].entries()) {
      const config=JSON.parse(fs.readFileSync(path.join(dir,`${node}.json`),'utf8'));
      const page=await browser.newPage({viewport:{width:390,height:844}});
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(`http://127.0.0.1:${basePort+index}/`);
      await page.getByLabel('Node access token').fill(config.token);
      await page.getByRole('button',{name:'Connect',exact:true}).click();
      await page.getByRole('heading',{name:`Hello, ${node}.`}).waitFor();
      pages[node]=page;
    }
    const alice=pages.alice;
    await alice.getByRole('link',{name:'03 / Clearing'}).click();
    await alice.getByLabel(privateProtocol ? 'Exact amount' : 'Maximum amount').fill('3');
    await alice.getByRole('button',{name:'Discover a loop',exact:true}).click();
    for (const node of ['alice','bob','doris']) {
      const page=pages[node];
      await page.getByRole('link',{name:'03 / Clearing'}).click();
      await page.getByRole('button',{name:'Approve test clearing',exact:true}).waitFor({timeout:20000});
      await page.locator('input[name=consent]').check();
      await page.getByRole('button',{name:'Approve test clearing',exact:true}).click();
    }
    for (const page of Object.values(pages)) {
      await page.getByRole('link',{name:'04 / Activity'}).click();
      await page.waitForFunction(text=>document.querySelector('#screen').textContent.includes(text), privateProtocol ? 'Applied locally · fulfillment verified' : 'Confirmed by all participants', {timeout:20000});
    }
    const downloadPromise=alice.waitForEvent('download');
    await alice.getByRole('button',{name:'Download receipt JSON'}).click();
    const download=await downloadPromise;
    const receipt=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
    assert.equal(receipt.mode,'testnet');
    if (privateProtocol) {
      assert.equal(receipt.receipt.local_fulfilled,true);
      assert.equal(receipt.receipt.protocol,'private-hashlock-v2');
      const r=receipt.receipt;
      const crypto=require('node:crypto');
      assert.equal(crypto.createHash('sha256').update(JSON.stringify({amount:r.amount,id:r.id,preimage:r.preimage,protocol:r.protocol,unit:r.unit})).digest('hex'),r.condition);
      await alice.route('**/api/state',async route=>{const response=await route.fetch();const body=await response.json();for(const r of body.receipts)if(r.status==='committed')r.preimage='00'.repeat(32);await route.fulfill({response,json:body});});
      await alice.waitForFunction(()=>document.querySelector('#screen').textContent.includes('Verification failed'),{},{timeout:15000});
      await alice.unroute('**/api/state');
      await alice.waitForFunction(()=>document.querySelector('#screen').textContent.includes('fulfillment verified'),{},{timeout:15000});
    } else assert.equal(receipt.receipt.cycle_complete,true);
    if (privateProtocol) {
    await alice.goto(`http://127.0.0.1:${basePort}/#peers`);
    await alice.getByRole('link',{name:'View history with bob',exact:true}).click();
    await alice.getByRole('heading',{name:privateProtocol ? 'Applied locally · fulfillment verified' : 'Confirmed by all participants',exact:true}).waitFor();
    assert.deepEqual(await alice.locator('#screen tbody tr td:first-child').allTextContents(),['bob']);
    const historyDownload=alice.waitForEvent('download');
    await alice.getByRole('button',{name:'Download local receipt',exact:true}).click();
    const historyReceipt=JSON.parse(fs.readFileSync(await(await historyDownload).path(),'utf8'));
    assert.equal(historyReceipt.receipt.id,receipt.receipt.id);
    await alice.setViewportSize({width:390,height:900});
    assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    if(process.env.APP_HISTORY_SCREENSHOT)await alice.screenshot({path:process.env.APP_HISTORY_SCREENSHOT,fullPage:true});
    }
    for (const width of [320,390,1280]) {
      await alice.setViewportSize({width,height:900});
      for (const screen of ['overview','peers','clearing','activity','settings']) {
        await alice.goto(`http://127.0.0.1:${basePort}/#${screen}`);
        await alice.waitForTimeout(100);
        assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${screen} at ${width}px overflows`);
      }
    }
    await alice.getByRole('button',{name:'Pause new clearing',exact:true}).click();
    await alice.getByRole('button',{name:'Resume new clearing',exact:true}).waitFor();
    await alice.context().setOffline(true);
    await alice.getByRole('link',{name:'03 / Clearing'}).click();
    assert.equal(await alice.getByRole('button',{name:'Discover a loop',exact:true}).isDisabled(),true);
    await alice.context().setOffline(false);
    assert.deepEqual(errors,[]);
    if (process.env.APP_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.APP_SCREENSHOT_DIR,{recursive:true});
      await alice.goto(`http://127.0.0.1:${basePort}/#activity`);
      await alice.getByRole('heading',{name:'Activity and receipts'}).waitFor();
      for (const [name,width] of [['desktop',1280],['mobile',390]]) {
        await alice.setViewportSize({width,height:900});
        await alice.screenshot({path:path.join(process.env.APP_SCREENSHOT_DIR,`${name}.png`),fullPage:true});
      }
    }
    console.log('PASS: three real browser sessions, approvals, confirmed receipts/export, 15 responsive layouts, pause and offline guards');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
