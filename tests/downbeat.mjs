import {createHash} from 'node:crypto';
import {chromium,browserPath,routeQaApi} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
await fs.mkdir('tests/output',{recursive:true});
import assert from 'node:assert/strict';
const suffix=process.env.QA_SUFFIX?'-'+process.env.QA_SUFFIX:'';
const output=name=>'tests/output/'+name.replace(/(\.[^.]+)$/,suffix+'$1');
const base=JSON.parse(await fs.readFile('tests/fixtures/ember-score.json','utf8'));
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({acceptDownloads:true,viewport:{width:1400,height:1000}}),page=await context.newPage(),errors=[],passed=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
await routeQaApi(page);
await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.route('**/api/jobs',r=>r.fulfill({status:202,json:{id:'e'.repeat(32)}}));
async function tools(){const tab=page.getByRole('tab',{name:'工具',exact:true});if(await tab.isVisible())await tab.click();}
async function scorePanel(){const tab=page.getByRole('tab',{name:'乐谱',exact:true});if(await tab.isVisible())await tab.click();}
async function load(){
  await page.goto(process.env.QA_BASE_URL||'http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();await page.getByRole('spinbutton',{name:'速度（BPM）'}).fill('68');await page.getByLabel('拍号',{exact:true}).selectOption('4/4');await page.getByLabel('调',{exact:true}).selectOption('C major');await page.getByRole('button',{name:'应用乐谱参数',exact:true}).click();await page.locator('.drop-zone[aria-disabled="false"]').waitFor();
  await page.locator('input[accept*="audio/mpeg"]').setInputFiles('tests/fixtures/ui-upload.flac');await page.waitForFunction(n=>Number(document.querySelector('.gf-score')?.dataset.mappedNotes)===n,base.noteCount);await tools();await page.locator('.score-settings summary').click();
}
async function request(kind,action){await tools();const response=page.waitForResponse(r=>r.url().endsWith('/'+kind));await action();const actual=await response;assert.equal(actual.status(),200);return actual.json();}
async function choose(id){await tools();if(!await page.locator('.navigation-settings').evaluate(e=>e.open))await page.locator('.navigation-settings summary').click();const element=page.locator(`.score-note[data-note-id="${id}"][data-anchor-onset="true"]`).first();await page.getByLabel('乐谱页码',{exact:true}).selectOption(await element.getAttribute('data-page'));await scorePanel();await element.evaluate(e=>e.scrollIntoView({block:'center'}));await element.click();}
async function waitScore(score){await page.waitForFunction(({fp,n})=>{const el=document.querySelector('.gf-score');return el?.dataset.scoreFingerprint===fp&&Number(el.dataset.mappedNotes)===n&&!document.body.innerText.includes('正在绘制乐谱');},{fp:score.scoreFingerprint,n:score.noteCount});}
async function downloadXml(){await tools();if(!await page.locator('.navigation-settings').evaluate(e=>e.open))await page.locator('.navigation-settings summary').click();await page.getByLabel('乐谱页码',{exact:true}).selectOption('1');const pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();const bytes=await fs.readFile(await(await pending).path());return {hash:createHash('sha256').update(bytes).digest('hex'),base64:bytes.toString('base64')};}

async function samePng(a,b){if(a.hash===b.hash)return;const close=await page.evaluate(async([one,two])=>{const images=await Promise.all([one,two].map(async value=>{const image=new Image();image.src='data:image/png;base64,'+value;await image.decode();return image;}));const canvas=document.createElement('canvas');canvas.width=620;canvas.height=877;const ctx=canvas.getContext('2d');ctx.drawImage(images[0],0,0,620,877);const first=ctx.getImageData(0,0,620,877).data;ctx.clearRect(0,0,620,877);ctx.drawImage(images[1],0,0,620,877);const second=ctx.getImageData(0,0,620,877).data;let differences=0;for(let i=0;i<first.length;i+=4)if(Math.max(Math.abs(first[i]-second[i]),Math.abs(first[i+1]-second[i+1]),Math.abs(first[i+2]-second[i+2]))>3)differences++;canvas.width=0;return differences/(620*877)<.00005;},[a.base64,b.base64]);assert.ok(close,'Restored page differs visually');}
async function newAnchor(id){
  await tools();await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();await choose(id);return request('rebar',()=>page.getByRole('button',{name:'重构乐谱',exact:true}).click());
}
try{
  await load();const original=await request('harmony',()=>page.getByRole('button',{name:'生成基本和弦',exact:true}).click());
  await page.waitForFunction(()=>!document.querySelector('.basic-harmony button.primary-button')?.disabled);
  const locked=await request('harmony',()=>page.getByLabel('和弦 2',{exact:true}).selectOption('5:7'));await page.waitForFunction(()=>!document.querySelector('.basic-harmony button.primary-button')?.disabled);
  await page.getByLabel('和弦偏移（毫秒；负值提前）',{exact:true}).fill('-250');
  const originalPlan=await request('harmony',()=>page.getByRole('button',{name:'应用对齐',exact:true}).click());
  await page.waitForFunction(()=>!document.querySelector('.basic-harmony button.primary-button')?.disabled);
  const originalPng=await downloadXml();const id='gf-000060',raw=base.notes.find(n=>n.id===id);
  await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();assert.equal(await page.getByRole('button',{name:'重构乐谱',exact:true}).isDisabled(),true);
  await choose(id);const floating=await page.getByRole('button',{name:'重构乐谱',exact:true}).boundingBox();assert.ok(floating.y>=0&&floating.y<1000);assert.equal(await page.locator('.gf-score').getAttribute('data-playing'),'false');assert.equal(await page.locator(`.anchor-selected[data-note-id="${id}"]`).count(),1);
  const continuation=page.locator('.score-note[data-anchor-onset="false"]').first();await page.getByLabel('乐谱页码',{exact:true}).selectOption(await continuation.getAttribute('data-page'));await continuation.evaluate(e=>e.scrollIntoView({block:'center'}));await continuation.click();await page.getByText('这是延音片段，请选择音符的真实起音。',{exact:true}).waitFor();
  await choose(id);
  await page.getByRole('button',{name:'试听附近旋律',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');await page.getByRole('button',{name:'停止',exact:true}).click();
  const result=await request('rebar',()=>page.getByRole('button',{name:'重构乐谱',exact:true}).click());await waitScore(result.score);
  assert.equal(result.score.downbeat.noteId,id);assert.equal(result.score.downbeat.time,raw.start);assert.deepEqual(result.score.events,base.events);
  const anchor=result.score.notes.find(n=>n.id===id),measure=result.score.measures[result.score.downbeat.measureNumber-1];assert.equal(anchor.startTick,measure.startTick);assert.ok(Math.abs(measure.start-raw.start)<.000001);
  assert.equal(result.harmony.alignment.offsetMs,0);assert.deepEqual(result.harmony.locks,{});assert.notEqual(result.score.scoreFingerprint,base.scoreFingerprint);
  assert.equal(await page.getByLabel('查看版本',{exact:true}).locator('option').count(),2);
  const start=page.locator(`.score-note[data-note-id="${id}"][data-anchor-onset="true"][data-measure="${measure.number}"]`).first();await start.waitFor();
  passed.push('Selecting a real melody onset rebuilds the full meter grid; tied continuations are rejected; original pitch/timing events are unchanged.');
  const reXml=await downloadXml();assert.ok(reXml.hash.length===64);assert.ok(result.harmony.xml.includes('implicit="yes"'));assert.ok(result.harmony.xml.includes('<staves>2</staves>'));
  await page.getByLabel('乐谱页码',{exact:true}).selectOption(await start.getAttribute('data-page'));await start.evaluate(e=>e.scrollIntoView({block:'center'}));await start.click();await page.waitForFunction(n=>document.querySelector('.gf-score')?.dataset.playing==='true'&&Number(document.querySelector('.gf-score').dataset.currentMeasure)===n,measure.number);
  const position=Number(await page.getByLabel('播放位置',{exact:true}).inputValue());assert.ok(position>=raw.start&&position<raw.start+.7);await page.getByRole('button',{name:'停止',exact:true}).evaluate(e=>e.click());
  await page.getByLabel('查看版本',{exact:true}).selectOption('0');await page.waitForFunction(fp=>document.querySelector('.gf-score')?.dataset.scoreFingerprint===fp,base.scoreFingerprint);
  assert.equal(await page.getByLabel('和弦偏移（毫秒；负值提前）',{exact:true}).inputValue(),'-250');assert.equal(await page.getByLabel('和弦 2',{exact:true}).inputValue(),'5:7');await samePng(await downloadXml(),originalPng);
  passed.push('Original score, locked chord and offset remain available; restored page is visually identical; rebuilt harmony resets old grid-specific locks/offset.');
  await page.getByLabel('查看版本',{exact:true}).selectOption('1');await waitScore(result.score);
  const edited=await request('harmony',()=>page.locator('[data-harmony-measure="2"] select').selectOption('1:major'));assert.equal(edited.sourceFingerprint,result.score.scoreFingerprint);assert.equal(edited.locks['2'],'1:major');
  await page.waitForFunction(()=>!document.querySelector('.basic-harmony button.primary-button')?.disabled);
  const secondId='gf-000090',second=await newAnchor(secondId);await waitScore(second.score);assert.equal(second.score.downbeat.noteId,secondId);assert.deepEqual(second.harmony.locks,{});assert.equal(await page.getByLabel('查看版本',{exact:true}).locator('option').count(),3);
  await page.getByLabel('查看版本',{exact:true}).selectOption('1');await waitScore(result.score);assert.equal(await page.locator('[data-harmony-measure="2"] select').inputValue(),'1:major');
  passed.push('Further corrections add independent score versions; harmony edits target the selected anchored grid.');
  await page.screenshot({path:output('downbeat-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(400);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await tools();await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();await choose(id);assert.ok(await page.locator('.anchor-selected').count());await tools();await page.getByRole('button',{name:'取消定位',exact:true}).click();
  await page.screenshot({path:output('downbeat-mobile.png'),fullPage:true});
  passed.push('390px layout supports selecting/cancelling a downbeat without horizontal page overflow.');
  await load();const restored=await request('rebar',()=>page.getByRole('button',{name:'恢复上次定位',exact:true}).click());await waitScore(restored.score);assert.equal(restored.score.downbeat.noteId,secondId);assert.equal(restored.harmony,null);
  const generated=await request('harmony',()=>page.getByRole('button',{name:'生成基本和弦',exact:true}).click());assert.equal(generated.sourceFingerprint,restored.score.scoreFingerprint);
  passed.push('The saved downbeat can be restored after re-uploading the same source; no models are rerun by reconstruction.');
  assert.deepEqual(errors,[]);await fs.writeFile(output('downbeat-checks.json'),JSON.stringify({passed,errors,browser:await browser.version(),noteCount:base.noteCount,selectedNoteId:id,selectedTime:raw.start,pickupSeconds:result.score.grid.phaseSeconds,syntheticDownbeat:true},null,2));console.log(passed.join('\n'));
}catch(error){await page.screenshot({path:output('downbeat-failure.png'),fullPage:true}).catch(()=>{});console.log('Browser errors',errors);throw error;}
finally{await browser.close();}
