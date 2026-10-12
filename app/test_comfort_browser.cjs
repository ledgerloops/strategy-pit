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
  async function save(page,peer,credit,min,max,auto=true){const form=page.locator(`form[data-contact="${peer}"]`);await form.locator('[name=credit_limit]').fill(String(credit));await form.locator('[name=comfort_min]').fill(String(min));await form.locator('[name=comfort_max]').fill(String(max));await form.locator('[name=auto_adjust]').setChecked(auto);await form.getByRole('button',{name:`Save preferences for ${peer}`,exact:true}).click();await page.waitForFunction(peer=>!document.querySelector(`form[data-contact="${peer}"] button[type=submit]`).disabled,peer);}
  await save(pages.alice,'bob',20,-5,15);await save(pages.bob,'alice',8,-10,8);
  async function expectedShared(page,peer,min,max,empty=false){await page.waitForFunction(async args=>{const token=sessionStorage.getItem('ledgerloops.testnet.token');const s=await(await fetch('/api/state',{headers:{Authorization:`Bearer ${token}`}})).json();const z=s.contacts.find(c=>c.peer===args.peer).shared_comfort;return z&&z.empty===args.empty&&(args.empty||z.min===args.min&&z.max===args.max)}, {peer,min,max,empty},{timeout:15000});await page.waitForTimeout(3200);}
  await expectedShared(pages.alice,'bob',-5,10);await expectedShared(pages.bob,'alice',-10,5);
  const alice=pages.alice;
  for(const width of[320,390,1280]){await alice.setViewportSize({width,height:900});assert.equal(await alice.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);}
  if(process.env.APP_SCREENSHOT_DIR){fs.mkdirSync(process.env.APP_SCREENSHOT_DIR,{recursive:true});for(const[name,width]of[['desktop',1280],['mobile',390]]){await alice.setViewportSize({width,height:900});await alice.screenshot({path:`${process.env.APP_SCREENSHOT_DIR}/${name}.png`,fullPage:true})}}
  await save(pages.bob,'alice',1,16,18,false);await expectedShared(alice,'bob',0,0,true);
  await alice.getByText('No shared comfort zone',{exact:false}).first().waitFor();
  await pages.bob.getByText('Existing debt remains',{exact:false}).first().waitFor();
  await alice.context().setOffline(true);await alice.waitForTimeout(100);assert.equal(await alice.locator('form[data-contact="bob"] button[type=submit]').isDisabled(),true);
  assert.deepEqual(errors,[]);console.log('PASS contact edits, mirrored shared zone, peer sync, no overlap, lowered cap, responsive layouts and offline guard');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
