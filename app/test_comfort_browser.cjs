const fs=require('node:fs');const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{
 const dir=process.env.APP_DEMO_DIR;if(!dir)throw Error('APP_DEMO_DIR required; use fresh private demo');
 const port=Number(process.env.APP_BASE_PORT||8961);
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
  const pages={},errors=[];
  for(const [i,node]of['alice','bob'].entries()){
   const p=await browser.newPage({viewport:{width:390,height:900}});p.on('pageerror',e=>errors.push(e.message));
   await p.goto(`http://127.0.0.1:${port+i}`);const c=JSON.parse(fs.readFileSync(`${dir}/${node}.json`));
   await p.getByLabel('Node access token').fill(c.token);await p.getByRole('button',{name:'Connect',exact:true}).click();
   await p.getByRole('heading',{name:`Hello, ${node}.`}).waitFor();await p.goto(`http://127.0.0.1:${port+i}/#peers`);pages[node]=p;
  }
  const snapshot=page=>page.evaluate(async()=>{
   const response=await fetch('/api/state',{headers:{Authorization:`Bearer ${sessionStorage.getItem('ledgerloops.testnet.token')}`}});
   return response.json();
  });
  const own=async(page,peer)=>(await snapshot(page)).contacts.find(c=>c.peer===peer).own;
  const saved=async(page,peer)=>{
   const form=page.locator(`form[data-contact="${peer}"]`);
   await form.locator('[data-contact-save]').filter({hasText:'Saved locally'}).waitFor();
   await page.waitForFunction(peer=>!document.querySelector(`form[data-contact="${peer}"] [name=credit_limit]`).disabled,peer);
  };
  async function save(page,peer,credit,min,max,auto=true){
   const form=page.locator(`form[data-contact="${peer}"]`);await form.locator('[data-scale=full]').click();
   await form.evaluate((form,{credit,min,max,auto})=>{
    for(const [name,value]of [['credit_limit',credit],['comfort_max',Math.max(0,max)],['comfort_min',min],['comfort_max',max]]){
     const el=form.elements[name];el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));
    }
    const checkbox=form.elements.auto_adjust;checkbox.checked=auto;
    checkbox.dispatchEvent(new Event('input',{bubbles:true}));
    checkbox.dispatchEvent(new Event('change',{bubbles:true}));
   },{credit,min,max,auto});
   await saved(page,peer);
   const preferences=await own(page,peer);
   assert.deepEqual([preferences.credit_limit,preferences.comfort_min,preferences.comfort_max,preferences.auto_adjust],[credit,min,max,auto]);
  }
  await save(pages.alice,'bob',20,-5,15);await save(pages.bob,'alice',8,-10,8);
  async function expectedShared(page,peer,min,max,empty=false){await page.waitForFunction(async args=>{const token=sessionStorage.getItem('ledgerloops.testnet.token');const s=await(await fetch('/api/state',{headers:{Authorization:`Bearer ${token}`}})).json();const z=s.contacts.find(c=>c.peer===args.peer).shared_comfort;return z&&z.empty===args.empty&&(args.empty||z.min===args.min&&z.max===args.max)}, {peer,min,max,empty},{timeout:15000});await page.waitForTimeout(3200);}
  await expectedShared(pages.alice,'bob',-5,10);await expectedShared(pages.bob,'alice',-10,5);
  const alice=pages.alice;
  const form=alice.locator('form[data-contact="bob"]');
  assert.equal(await form.locator('input[type=number]').count(),0);
  assert.equal(await form.locator('button[type=submit]').count(),0,'no Save button');
  await form.locator('[data-scale=fit]').click();
  const dot=form.locator('[name=comfort_min]');
  // A draft survives navigation while an input gesture has not been released.
  await dot.evaluate(el=>{el.value=-4;el.dispatchEvent(new Event('input',{bubbles:true}));});assert.equal(await dot.inputValue(),'-4');
  await alice.getByRole('link',{name:'View history with bob',exact:true}).click();
  await alice.getByText('No clearing history for this contact',{exact:false}).waitFor();
  await alice.getByRole('link',{name:'← Back to contact preferences'}).click();assert.equal(await dot.inputValue(),'-4');
  await form.locator('[data-reset-contact]').click();assert.equal(await dot.inputValue(),'-5');
  let posts=0;alice.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/api/contacts/bob/preferences'))posts++;});
  const beforeDrag=await own(alice,'bob');
  await dot.scrollIntoViewIfNeeded();const box=await dot.boundingBox();const limits=await dot.evaluate(el=>({min:Number(el.min),max:Number(el.max),value:Number(el.value)}));const handleX=box.x+14+(box.width-28)*(limits.value-limits.min)/(limits.max-limits.min);await alice.mouse.move(handleX,box.y+box.height/2);await alice.mouse.down();await alice.mouse.move(box.x+box.width*0.25,box.y+box.height/2,{steps:8});
  await alice.waitForTimeout(3500);assert.equal(posts,0,'no write while pointer is held, including polling');
  assert.deepEqual(await own(alice,'bob'),beforeDrag);
  await alice.mouse.up();assert.notEqual(await dot.inputValue(),'-5');
  await saved(alice,'bob');assert.equal(posts,1,'one write after drag release');
  assert.equal((await own(alice,'bob')).comfort_min,Number(await dot.inputValue()));
  await save(alice,'bob',20,-5,20);
  await form.locator('[data-scale=fit]').click();
  await form.locator('[data-scale=wider]').click();
  const maximum=form.locator('[name=comfort_max]'),limit=form.locator('[name=credit_limit]');
  await maximum.focus();await maximum.press('ArrowRight');
  assert.equal(await maximum.inputValue(),'21');assert.equal(await limit.inputValue(),'21','comfort pulls credit maximum along');
  await saved(alice,'bob');assert.equal((await own(alice,'bob')).credit_limit,21);
  assert.equal(await maximum.evaluate(el=>el===document.activeElement),true,'keyboard focus restored after save');
  await limit.focus();await limit.press('ArrowLeft');assert.equal(await maximum.inputValue(),'20');
  await saved(alice,'bob');
  await save(alice,'bob',20,16,18);
  await limit.evaluate(el=>{el.value=3;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
  assert.equal(await maximum.inputValue(),'3');assert.equal(await dot.inputValue(),'3','lower credit pulls both positive comfort endpoints');
  await saved(alice,'bob');
  await alice.reload();await maximum.waitFor();
  assert.equal(await maximum.inputValue(),'3');assert.equal(await dot.inputValue(),'3');assert.equal(await limit.inputValue(),'3');
  await save(alice,'bob',20,-5,15);

  const zeroForm=alice.locator('form[data-contact="doris"]');
  await zeroForm.locator('[name=comfort_min]').focus();await zeroForm.locator('[name=comfort_min]').press('ArrowLeft');
  await zeroForm.locator('[name=comfort_max]').focus();await zeroForm.locator('[name=comfort_max]').press('ArrowRight');
  assert.equal(await zeroForm.locator('[name=comfort_min]').inputValue(),'-1');
  assert.equal(await zeroForm.locator('[name=comfort_max]').inputValue(),'1');
  await saved(alice,'doris');
  await save(alice,'doris',0,0,0,false);
  for(const width of[320,390,1280]){await alice.setViewportSize({width,height:900});assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);}
  if(process.env.APP_SCREENSHOT_DIR){fs.mkdirSync(process.env.APP_SCREENSHOT_DIR,{recursive:true});for(const[name,width]of[['desktop',1280],['mobile',390]]){await alice.setViewportSize({width,height:900});await alice.screenshot({path:`${process.env.APP_SCREENSHOT_DIR}/${name}.png`,fullPage:true});if(name==='mobile')await alice.locator('.contact').first().screenshot({path:`${process.env.APP_SCREENSHOT_DIR}/contact-diagram.png`})}}
  await save(pages.bob,'alice',1,-18,-16,false);await expectedShared(alice,'bob',0,0,true);
  await form.locator('.comfort-preview').filter({hasText:'No shared comfort zone'}).waitFor();
  await pages.bob.getByText('Existing debt remains',{exact:false}).first().waitFor();
  // Rejected writes retain the draft and offer retry rather than claiming success.
  const beforeFailure=await own(alice,'bob');
  await alice.route('**/api/contacts/bob/preferences',route=>route.fulfill({status:400,json:{error:'Injected preference rejection'}}));
  await dot.focus();await dot.press('ArrowRight');
  await form.locator('[data-contact-save]').filter({hasText:'Not saved: Injected preference rejection'}).waitFor();
  assert.deepEqual(await own(alice,'bob'),beforeFailure);
  assert.equal(await dot.inputValue(),'-4');
  await alice.unroute('**/api/contacts/bob/preferences');
  await form.getByRole('button',{name:'Retry automatic save',exact:true}).click();await saved(alice,'bob');
  assert.equal((await own(alice,'bob')).comfort_min,-4);
  // A committed POST with a lost response is reconciled by GET, without resubmitting.
  const postsBeforeLostAck=posts;
  await alice.route('**/api/contacts/bob/preferences',async route=>{await route.fetch();await route.fulfill({status:503,json:{error:'Committed response lost at gateway'}});});
  await dot.focus();await dot.press('ArrowRight');
  await form.locator('[data-contact-save]').filter({hasText:'Save not confirmed'}).waitFor();
  await alice.unroute('**/api/contacts/bob/preferences');
  await saved(alice,'bob');assert.equal(posts,postsBeforeLostAck+1);
  assert.equal((await own(alice,'bob')).comfort_min,-3);
  // Finishing one contact's save must not steal focus from another contact.
  let releaseSave;
  const saveBarrier=new Promise(resolve=>{releaseSave=resolve;});
  await alice.route('**/api/contacts/bob/preferences',async route=>{await saveBarrier;await route.continue();});
  await dot.focus();await dot.press('ArrowRight');
  await form.locator('[data-contact-save]').filter({hasText:'Saving preferences'}).waitFor();
  const otherMaximum=zeroForm.locator('[name=comfort_max]');await otherMaximum.focus();
  releaseSave();await saved(alice,'bob');
  assert.equal(await otherMaximum.evaluate(el=>el===document.activeElement),true);
  await alice.unroute('**/api/contacts/bob/preferences');
  // Large stored values survive a reload and scale changes without silent clamping.
  await save(alice,'bob',1000000000000,-1000000000000,1000000000000,false);
  await alice.reload();await alice.locator('form[data-contact="bob"] [name=credit_limit]').waitFor();
  assert.equal(await form.locator('[name=credit_limit]').inputValue(),'1000000000000');
  assert.equal(await form.locator('[name=comfort_min]').inputValue(),'-1000000000000');
  assert.equal(await form.locator('[name=comfort_max]').inputValue(),'1000000000000');
  await alice.context().setOffline(true);await alice.waitForTimeout(100);assert.equal(await limit.isDisabled(),true);
  assert.deepEqual(errors,[]);console.log('PASS linked maximum, automatic save on release, keyboard focus, reload persistence, rejection/retry, lost-response recovery, mirrored zones, responsive layouts and offline guard');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
