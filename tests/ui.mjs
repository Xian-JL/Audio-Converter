import {createHash} from 'node:crypto';
import {chromium,browserPath,routeQaApi} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
await fs.mkdir('tests/output',{recursive:true});
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const page=await browser.newPage({viewport:{width:1400,height:1000},acceptDownloads:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
await routeQaApi(page);
await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.route('**/api/jobs',r=>r.fulfill({status:202,json:{id:'e'.repeat(32)}}));
async function request(kind,action){if(await page.getByRole('tab',{name:'工具',exact:true}).isVisible())await page.getByRole('tab',{name:'工具',exact:true}).click();const pending=page.waitForResponse(r=>r.url().endsWith('/'+kind),{timeout:120000});await action();const r=await pending;assert.equal(r.status(),200);return r.json();}
async function xml(){await page.getByLabel('乐谱页码',{exact:true}).selectOption('1');const pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();const bytes=await fs.readFile(await(await pending).path());return {hash:createHash('sha256').update(bytes).digest('hex'),base64:bytes.toString('base64')};}

async function samePng(a,b){if(a.hash===b.hash)return;const close=await page.evaluate(async([one,two])=>{const images=await Promise.all([one,two].map(async value=>{const image=new Image();image.src='data:image/png;base64,'+value;await image.decode();return image;}));const canvas=document.createElement('canvas');canvas.width=620;canvas.height=877;const ctx=canvas.getContext('2d');ctx.drawImage(images[0],0,0,620,877);const first=ctx.getImageData(0,0,620,877).data;ctx.clearRect(0,0,620,877);ctx.drawImage(images[1],0,0,620,877);const second=ctx.getImageData(0,0,620,877).data;let differences=0;for(let i=0;i<first.length;i+=4)if(Math.max(Math.abs(first[i]-second[i]),Math.abs(first[i+1]-second[i+1]),Math.abs(first[i+2]-second[i+2]))>3)differences++;canvas.width=0;return differences/(620*877)<.00005;},[a.base64,b.base64]);assert.ok(close,'Restored page differs visually');}
async function settled(){await page.waitForFunction(()=>!document.body.innerText.includes('正在绘制乐谱')&&!document.querySelector('.basic-harmony button.primary-button')?.disabled);}
try{
  await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();
  await page.getByRole('spinbutton',{name:'速度（BPM）'}).fill('68');await page.getByLabel('拍号',{exact:true}).selectOption('4/4');await page.getByLabel('调',{exact:true}).selectOption('C major');await page.getByRole('button',{name:'应用乐谱参数',exact:true}).click();
  await page.locator('.drop-zone[aria-disabled="false"]').waitFor();await page.locator('input[accept*="audio/mpeg"]').setInputFiles('tests/fixtures/ui-upload.flac');await page.locator('.score-note').first().waitFor();await page.locator('.score-settings summary').click();
  await request('harmony',()=>page.getByRole('button',{name:'生成基本和弦',exact:true}).click());await settled();
  const block=await request('harmony',()=>page.getByLabel('和弦 2',{exact:true}).selectOption('5:7'));await settled();const blockPng=await xml();
  const take=await request('texture',()=>page.getByRole('button',{name:'生成丰富伴奏',exact:true}).click());await settled();
  assert.equal(take.harmonyFingerprint,block.fingerprint);assert.equal(take.settings.style,'lyrical');assert.ok(take.events.length>block.events.length);const takePng=await xml();assert.notEqual(takePng.hash,blockPng.hash);
  assert.equal(await page.getByLabel('和弦 2',{exact:true}).inputValue(),'5:7');
  await page.getByLabel('试听版本',{exact:true}).selectOption('-1');await settled();await samePng(await xml(),blockPng);
  await page.getByLabel('试听版本',{exact:true}).selectOption('0');await settled();await samePng(await xml(),takePng);
  const note=page.locator('.score-note[data-measure="4"]').first();await note.evaluate(e=>e.scrollIntoView({block:'center'}));await note.click();
  await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true'&&document.querySelector('.gf-score')?.dataset.currentMeasure==='4');await page.getByRole('button',{name:'停止',exact:true}).evaluate(e=>e.click());
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出编配',exact:true}).click();const exported=JSON.parse(await fs.readFile(await(await download).path(),'utf8'));assert.equal(exported.accompaniment.fingerprint,take.fingerprint);
  await page.getByLabel('织体倾向',{exact:true}).selectOption('flowing');await page.getByLabel('密度',{exact:true}).selectOption('2');await page.getByLabel('备选方案',{exact:true}).selectOption('2');
  const second=await request('texture',()=>page.getByRole('button',{name:'生成丰富伴奏',exact:true}).click());await settled();const secondPng=await xml();assert.notDeepEqual(second.events,take.events);assert.equal(await page.getByLabel('试听版本',{exact:true}).locator('option').count(),3);
  await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();const anchor=page.locator('.score-note[data-note-id="gf-000060"][data-anchor-onset="true"]').first();await page.getByLabel('乐谱页码',{exact:true}).selectOption(await anchor.getAttribute('data-page'));await anchor.evaluate(e=>e.scrollIntoView({block:'center'}));await anchor.click();
  const rebuilt=await request('rebar',()=>page.getByRole('button',{name:'重构乐谱',exact:true}).click());await settled();assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'-1');
  const anchored=await request('texture',()=>page.getByRole('button',{name:'生成丰富伴奏',exact:true}).click());await settled();assert.equal(anchored.sourceFingerprint,rebuilt.score.scoreFingerprint);assert.equal(anchored.harmonyFingerprint,rebuilt.harmony.fingerprint);assert.ok((await xml()).hash.length===64);
  await page.getByLabel('查看版本',{exact:true}).selectOption('0');await settled();assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'1');await samePng(await xml(),secondPng);
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(500);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'tests/output/studio-mobile.png',fullPage:true});
  await request('harmony',()=>page.getByLabel('和弦 2',{exact:true}).selectOption('1:major'));await settled();assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'-1');assert.equal(await page.getByLabel('试听版本',{exact:true}).locator('option').count(),1);
  await page.setViewportSize({width:1400,height:1000});await page.screenshot({path:'tests/output/studio-desktop.png',fullPage:true});assert.deepEqual(errors,[]);
  await fs.writeFile('tests/output/browser-checks'+(process.env.QA_SUFFIX?'-'+process.env.QA_SUFFIX:'')+'.json',JSON.stringify({browser:await browser.version(),checks:['real CPU API generation','locked harmony unchanged','PNG exports active arrangement','block reference restored visually','multiple distinct alternatives','bar click starts playback','JSON export','390px no overflow','harmony edit invalidates stale arrangement'],errors,seconds:take.generationSeconds},null,2));console.log('v13 browser checks passed');
}finally{await browser.close();}
