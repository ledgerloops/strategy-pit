/* Real LedgerLoops UI capture. Creates and removes its own isolated fixture only.
 * From the repository root:
 *   CHROMIUM_PATH=/usr/bin/chromium node artifacts/mdg2-2026-10-25/capture-comfort-ui.cjs
 * Requires Python 3 and Playwright. Never prints or saves credentials in artifacts.
 */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawn,spawnSync} = require('node:child_process');
const {chromium} = require('playwright');

const output = __dirname;
const repository = path.resolve(output,'../..');
const sensitiveValues = [];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve,milliseconds));
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

(async () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(),'ledgerloops-mdg2-capture-'));
  const nodes = ['alice','bob','doris'];
  const ports = {};
  for (const name of nodes) {
    do { ports[name] = await freePort(); } while (Object.values(ports).filter(port => port === ports[name]).length > 1);
  }
  const children = [];
  let browser;
  try {
    const setup = spawnSync('python3',['-c',String.raw`
import json,sys
from pathlib import Path
from private_node import Node
from run_demo import create_configs
directory=Path(sys.argv[1]); ports=json.loads(sys.argv[2])
configs=create_configs(directory,ports)
for name,config in configs.items():
    for peer,details in config['peers'].items():
        details['balance']=-3 if (name,peer)==('alice','bob') else 3 if (name,peer)==('bob','alice') else 0
    (directory/(name+'.json')).write_text(json.dumps(config,indent=2)+'\n')
    node=Node(config,directory/(name+'.sqlite'))
    try:
        for peer in config['peers']:
            values=dict(credit_limit=10,comfort_min=0,comfort_max=0,auto_adjust=False)
            if (name,peer)==('alice','bob'): values=dict(credit_limit=20,comfort_min=-5,comfort_max=15,auto_adjust=True)
            if (name,peer)==('bob','alice'): values=dict(credit_limit=8,comfort_min=-10,comfort_max=8,auto_adjust=True)
            node.set_preferences(peer,dict(values,expected_revision=1))
    finally: node.db.close()
`,fixture,JSON.stringify(ports)],{cwd:path.join(repository,'app'),encoding:'utf8'});
    if (setup.status !== 0) throw Error('Isolated fixture setup failed: '+setup.stderr);
    const configs = Object.fromEntries(nodes.map(name => [name,JSON.parse(fs.readFileSync(path.join(fixture,name+'.json')))]));
    for (const config of Object.values(configs)) sensitiveValues.push(config.token,...Object.values(config.peers).map(peer => peer.key));
    for (const name of nodes) children.push(spawn('python3',[
      path.join(repository,'app/private_node.py'),'--config',path.join(fixture,name+'.json'),
      '--db',path.join(fixture,name+'.sqlite'),'--host','127.0.0.1','--port',String(ports[name])
    ],{stdio:'ignore'}));
    browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
    const context = await browser.newContext({viewport:{width:1440,height:1800},deviceScaleFactor:2,locale:'en-GB',timezoneId:'Europe/Amsterdam',reducedMotion:'reduce'});
    const origin = `http://127.0.0.1:${ports.alice}`;
    let fixtureState;
    for (let attempt = 0; attempt < 150; attempt++) {
      try {
        const response = await context.request.get(origin+'/api/state',{headers:{Authorization:'Bearer '+configs.alice.token},timeout:1000});
        const next = await response.json();
        const contact = next.contacts?.find(contact => contact.peer === 'bob');
        if (contact?.shared_comfort?.min === -5 && contact.shared_comfort.max === 10) {fixtureState = contact; break;}
      } catch (_) { /* Servers and durable neighbour preference messages are still starting. */ }
      await delay(100);
    }
    if (!fixtureState) throw Error('Isolated fixture did not synchronize shared comfort [-5,10]');
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror',error => pageErrors.push(error.message));
    await page.goto(origin);
    await page.getByLabel('Node access token').fill(configs.alice.token);
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.getByRole('heading',{name:'Hello, alice.',exact:true}).waitFor();
    await page.getByRole('link',{name:'02 / Peers',exact:true}).click();
    const form = page.locator('form[data-contact="bob"]');
    const card = page.locator('article.contact').filter({has:form});
    await form.locator('[data-scale="fit"]').click();
    await form.locator('.comfort-preview').filter({hasText:'You owe 5 TEST → Owes you 10 TEST'}).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.mouse.move(10,10);
    await page.locator('#title').click();
    if (await page.locator('input[name="token"]').count()) throw Error('Login UI must not appear in screenshots');
    if (pageErrors.length) throw Error('Browser errors: '+pageErrors.join('; '));
    // Native page geometry only: this crops from the existing legend through values.
    const axis = form.locator('.preference-axis');
    await axis.scrollIntoViewIfNeeded();
    const axisBox = await axis.boundingBox();
    const valuesBox = await form.locator('.diagram-values').boundingBox();
    const primaryClip = {x:axisBox.x-16,y:axisBox.y,width:axisBox.width+32,height:valuesBox.y+valuesBox.height-axisBox.y};
    await page.screenshot({path:path.join(output,'comfort-zone-ui.png'),clip:primaryClip});
    await card.screenshot({path:path.join(output,'comfort-zone-ui-contact.png')});
    await page.setViewportSize({width:1440,height:1000});
    await page.evaluate(() => scrollTo(0,0));
    await page.screenshot({path:path.join(output,'comfort-zone-ui-wide.png')});
    const sourceFiles = ['app/static/app.js','app/static/index.html','app/static/style.css','app/private_node.py','app/comfort.py'];
    const sourceCommit = spawnSync('git',['rev-parse','HEAD'],{cwd:repository,encoding:'utf8'}).stdout.trim();
    const screenshotNames = ['comfort-zone-ui.png','comfort-zone-ui-contact.png','comfort-zone-ui-wide.png'];
    const images = screenshotNames.map(name => {
      const file = path.join(output,name),bytes = fs.readFileSync(file);
      return {file:name,width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20),sha256:sha256(file)};
    });
    const provenance = {
      source_commit:sourceCommit,captured_at:new Date().toISOString(),browser:await browser.version(),
      viewport_css_pixels:{detail_and_contact:{width:1440,height:1800},wide:{width:1440,height:1000}},device_scale_factor:2,
      capture:'Real authenticated private-hashlock-v2 application served by three live Python nodes with durable neighbour HTTP preference exchange. No DOM, CSS or text changes; screenshot crops use native element geometry.',
      fixture:{isolated:true,ephemeral_credentials_removed_after_capture:true,node:'alice',peer:'bob',balance:-3,own:{credit_limit:20,comfort_min:-5,comfort_max:15,auto_adjust:true},peer_preferences:{credit_limit:8,comfort_min:-10,comfort_max:8,auto_adjust:true},shared_comfort:{min:-5,max:10}},
      source_file_sha256:Object.fromEntries(sourceFiles.map(file => [file,sha256(path.join(repository,file))])),images,
      limitations:['TEST-only research prototype; preconfigured participants and honest-peer assumptions.','Fabricated screenshot fixture; not real economic activity.','Screenshot demonstrates saved UI preferences and a shared-zone calculation; it does not demonstrate a clearing settlement.']
    };
    fs.writeFileSync(path.join(output,'comfort-zone-ui-provenance.json'),JSON.stringify(provenance,null,2)+'\n');
    console.log(JSON.stringify({source_commit:sourceCommit,images}));
  } finally {
    if (browser) await browser.close();
    for (const child of children) child.kill('SIGTERM');
    await Promise.all(children.map(child => child.exitCode !== null ? Promise.resolve() : new Promise(resolve => child.once('exit',resolve))));
    fs.rmSync(fixture,{recursive:true,force:true});
  }
})().catch(error => {
  let message = String(error.stack || error);
  for (const value of sensitiveValues) if (value) message = message.split(value).join('[redacted]');
  console.error(message); process.exitCode = 1;
});
