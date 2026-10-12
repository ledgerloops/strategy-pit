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
  async function save(page,peer,credit,min,max,auto=true){const form=page.locator(`form[data-contact="${peer}"]`);await form.locator('[data-scale=full]').click();for(const [name,value] of [['credit_limit',credit],['comfort_max',Math.max(0,max)],['comfort_min',min],['comfort_max',max]]){await form.locator(`[name=${name}]`).evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));},String(value));}await form.locator('[name=auto_adjust]').setChecked(auto);await form.getByRole('button',{name:`Save preferences for ${peer}`,exact:true}).click();await page.waitForFunction(peer=>!document.querySelector(`form[data-contact="${peer}"] button[type=submit]`).disabled,peer);}
  await save(pages.alice,'bob',20,-5,15);await save(pages.bob,'alice',8,-10,8);
  async function expectedShared(page,peer,min,max,empty=false){await page.waitForFunction(async args=>{const token=sessionStorage.getItem('ledgerloops.testnet.token');const s=await(await fetch('/api/state',{headers:{Authorization:`Bearer ${token}`}})).json();const z=s.contacts.find(c=>c.peer===args.peer).shared_comfort;return z&&z.empty===args.empty&&(args.empty||z.min===args.min&&z.max===args.max)}, {peer,min,max,empty},{timeout:15000});await page.waitForTimeout(3200);}
  await expectedShared(pages.alice,'bob',-5,10);await expectedShared(pages.bob,'alice',-10,5);
  const alice=pages.alice;
  const form=alice.locator('form[data-contact="bob"]');
  assert.equal(await form.locator('input[type=number]').count(),0);
  await form.locator('[data-scale=fit]').click();
  const dot=form.locator('[name=comfort_min]');await dot.focus();await dot.press('ArrowRight');assert.equal(await dot.inputValue(),'-4');
  await alice.getByRole('link',{name:'View history with bob',exact:true}).click();
  await alice.getByText('No clearing history for this contact',{exact:false}).waitFor();
  await alice.getByRole('link',{name:'← Back to contact preferences'}).click();assert.equal(await dot.inputValue(),'-4');
  await form.locator('[data-reset-contact]').click();assert.equal(await dot.inputValue(),'-5');
  await dot.scrollIntoViewIfNeeded();const box=await dot.boundingBox();const limits=await dot.evaluate(el=>({min:Number(el.min),max:Number(el.max),value:Number(el.value)}));const handleX=box.x+14+(box.width-28)*(limits.value-limits.min)/(limits.max-limits.min);await alice.mouse.move(handleX,box.y+box.height/2);await alice.mouse.down();await alice.mouse.move(box.x+box.width*0.25,box.y+box.height/2,{steps:8});await alice.mouse.up();assert.notEqual(await dot.inputValue(),'-5');
  await form.locator('[data-reset-contact]').click();

  const zeroForm=alice.locator('form[data-contact="doris"]');
  await zeroForm.locator('[name=comfort_min]').focus();await zeroForm.locator('[name=comfort_min]').press('ArrowLeft');
  await zeroForm.locator('[name=comfort_max]').focus();await zeroForm.locator('[name=comfort_max]').press('ArrowRight');
  assert.equal(await zeroForm.locator('[name=comfort_min]').inputValue(),'-1');
  assert.equal(await zeroForm.locator('[name=comfort_max]').inputValue(),'1');
  await zeroForm.locator('[data-reset-contact]').click();
  for(const width of[320,390,1280]){await alice.setViewportSize({width,height:900});assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);}
  if(process.env.APP_SCREENSHOT_DIR){fs.mkdirSync(process.env.APP_SCREENSHOT_DIR,{recursive:true});for(const[name,width]of[['desktop',1280],['mobile',390]]){await alice.setViewportSize({width,height:900});await alice.screenshot({path:`${process.env.APP_SCREENSHOT_DIR}/${name}.png`,fullPage:true});if(name==='mobile')await alice.locator('.contact').first().screenshot({path:`${process.env.APP_SCREENSHOT_DIR}/contact-diagram.png`})}}
  await save(pages.bob,'alice',1,16,18,false);await expectedShared(alice,'bob',0,0,true);
  await form.locator('.comfort-preview').filter({hasText:'No shared comfort zone'}).waitFor();
  await pages.bob.getByText('Existing debt remains',{exact:false}).first().waitFor();
  // Large stored values survive a reload and scale changes without silent clamping.
  await save(alice,'bob',1000000000000,-1000000000000,1000000000000,false);
  await alice.reload();await alice.locator('form[data-contact="bob"] [name=credit_limit]').waitFor();
  assert.equal(await form.locator('[name=credit_limit]').inputValue(),'1000000000000');
  assert.equal(await form.locator('[name=comfort_min]').inputValue(),'-1000000000000');
  assert.equal(await form.locator('[name=comfort_max]').inputValue(),'1000000000000');
  await alice.context().setOffline(true);await alice.waitForTimeout(100);assert.equal(await alice.locator('form[data-contact="bob"] button[type=submit]').isDisabled(),true);
  assert.deepEqual(errors,[]);console.log('PASS contact edits, mirrored shared zone, peer sync, no overlap, lowered cap, responsive layouts and offline guard');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
