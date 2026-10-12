/* Real three-node browser integration. Requires fresh app/run_comfort_demo.py network. */
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {chromium}=require('playwright');
(async()=>{
 const directory=process.env.APP_DEMO_DIR;
 if(!directory)throw Error('APP_DEMO_DIR must point to a fresh comfort demo directory');
 const port=Number(process.env.APP_BASE_PORT||8991);
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 const pages={},errors=[];
 const snapshot=page=>page.evaluate(async()=>{
  const r=await fetch('/api/state',{headers:{Authorization:`Bearer ${sessionStorage.getItem('ledgerloops.testnet.token')}`},cache:'no-store'});
  if(!r.ok)throw Error(`State unavailable: ${r.status}`);
  return r.json();
 });
 try{
  for(const [i,node]of ['alice','bob','doris'].entries()){
   const config=JSON.parse(fs.readFileSync(path.join(directory,`${node}.json`),'utf8'));
   const page=await browser.newPage({viewport:{width:390,height:900}});
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(`http://127.0.0.1:${port+i}`);
   await page.getByLabel('Node access token').fill(config.token);
   await page.getByRole('button',{name:'Connect',exact:true}).click();
   await page.getByRole('heading',{name:`Hello, ${node}.`}).waitFor();
   pages[node]=page;
  }
  const before=await Promise.all(Object.values(pages).map(snapshot));
  assert.equal(before.flatMap(s=>s.balances).reduce((sum,b)=>sum+Math.max(0,b.balance),0),2,'fixture must start with debt 2');
  const alice=pages.alice;
  await alice.getByRole('link',{name:'03 / Clearing'}).click();
  assert.equal(await alice.getByLabel('Reduce existing debt',{exact:true}).isChecked(),true);
  await alice.getByLabel('Move toward shared comfort',{exact:true}).check();
  await alice.getByLabel('Exact amount').fill('2');
  await alice.getByRole('button',{name:'Discover a loop',exact:true}).click();
  for(const page of Object.values(pages)){
   await page.getByRole('link',{name:'03 / Clearing'}).click();
   await page.getByRole('button',{name:'Approve test clearing',exact:true}).waitFor({timeout:20000});
   await page.getByRole('heading',{name:'Comfort adjustment · manual approval',exact:true}).waitFor();
   assert.equal(await page.locator('.comfort-terms details').count(),2);
  }
  const pending=await Promise.all(Object.values(pages).map(snapshot));
  assert.equal(pending.flatMap(s=>s.receipts).length,0,'assistance permission must not automatically execute');
  for(const [i,node]of ['alice','bob','doris'].entries()){
   await pages[node].locator('input[name=consent]').check();
   await pages[node].getByRole('button',{name:'Approve test clearing',exact:true}).click();
   if(i===1)assert.equal((await Promise.all(Object.values(pages).map(snapshot))).flatMap(s=>s.receipts).length,0,'two approvals cannot settle three nodes');
  }
  for(const page of Object.values(pages)){
   await page.getByRole('link',{name:'04 / Activity'}).click();
   await page.waitForFunction(()=>document.querySelector('#screen').textContent.includes('Applied locally · fulfillment verified'),null,{timeout:20000});
  }
  const after=await Promise.all(Object.values(pages).map(snapshot));
  assert.equal(after.flatMap(s=>s.balances).reduce((sum,b)=>sum+Math.max(0,b.balance),0),4,'comfort improvement legitimately increases gross debt');
  for(let i=0;i<after.length;i++){
   assert.equal(after[i].balances.reduce((sum,b)=>sum+b.balance,0),before[i].balances.reduce((sum,b)=>sum+b.balance,0));
   assert.equal(after[i].receipts.length,1);
   const receipt=after[i].receipts[0];
   assert.equal(receipt.clearing_mode,'comfort');
   assert.equal(receipt.policy,'bilateral-comfort-v1');
   assert.equal(receipt.hashlock_scheme,'sha256-comfort-v1');
   assert.equal(receipt.local_fulfilled,true);
   assert.ok(receipt.changes.every(c=>c.discomfort_after===0));
   const canonical={amount:receipt.amount,clearing_mode:receipt.clearing_mode,direction:receipt.direction,id:receipt.id,policy:receipt.policy,preimage:receipt.preimage,protocol:receipt.protocol,unit:receipt.unit};
   assert.equal(crypto.createHash('sha256').update(JSON.stringify(canonical)).digest('hex'),receipt.condition);
  }
  const downloadEvent=alice.waitForEvent('download');
  await alice.getByRole('button',{name:'Download receipt JSON'}).click();
  const exported=JSON.parse(fs.readFileSync(await(await downloadEvent).path(),'utf8'));
  assert.equal(exported.receipt.condition,after[0].receipts[0].condition);
  // A changed comfort direction must fail independent browser verification.
  await alice.route('**/api/state',async route=>{
   const response=await route.fetch();const data=await response.json();
   for(const receipt of data.receipts)receipt.direction=-receipt.direction;
   await route.fulfill({response,json:data});
  });
  await alice.waitForFunction(()=>document.querySelector('#screen').textContent.includes('Verification failed'),null,{timeout:15000});
  await alice.unroute('**/api/state');
  await alice.waitForFunction(()=>document.querySelector('#screen').textContent.includes('Applied locally · fulfillment verified'),null,{timeout:15000});
  if(process.env.APP_SCREENSHOT_DIR){fs.mkdirSync(process.env.APP_SCREENSHOT_DIR,{recursive:true});await alice.screenshot({path:path.join(process.env.APP_SCREENSHOT_DIR,'settlement.png'),fullPage:true});}
  await alice.goto(`http://127.0.0.1:${port}/#history/bob`);
  await alice.getByRole('heading',{name:'History with bob',exact:true}).waitFor();
  assert.deepEqual(await alice.locator('#screen tbody tr td:first-child').allTextContents(),['bob']);
  assert.equal(await alice.locator('.comfort-terms h4').textContent(),'bob');
  for(const width of [320,390,1280]){await alice.setViewportSize({width,height:900});assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  assert.deepEqual(errors,[]);
  console.log('PASS real comfort discovery, three manual approvals, debt 2→4, zero final discomfort, conserved net positions, bound fulfillment verification, tamper rejection, receipt export and scoped history');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
