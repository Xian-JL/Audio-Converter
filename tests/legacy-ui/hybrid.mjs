// Historical UI scenario. See ../README.md for the maintained v0.7.2 suite.
import {chromium,browserPath,routeQaApi} from '../browser-runtime.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const qa=process.env.QA_API_URL||'http://127.0.0.1:8770';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true});
page.setDefaultTimeout(60000);const errors=[],warnings=[],progress=[];let opened;
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='warning'&&m.text().includes('Preserving source engraving'))warnings.push(m.text());});
await routeQaApi(page,qa);
page.on('response',async r=>{if(r.url().endsWith('/progress')){try{progress.push(await r.json());}catch{}}});
await page.route('**/api/projects/open',async route=>{const response=await route.fetch({url:qa+'/api/projects/open',headers:{...route.request().headers(),origin:'http://127.0.0.1:8765'},timeout:0});assert.equal(response.status(),200,await response.text());opened=await response.json();await route.fulfill({json:opened});});
await page.route('**/api/jobs/*/texture',async route=>{const body=route.request().postDataJSON();body.seed=20261028;const headers={...route.request().headers(),origin:'http://127.0.0.1:8765'};delete headers['content-length'];const response=await route.fetch({url:qa+new URL(route.request().url()).pathname,headers,postData:JSON.stringify(body),timeout:0});await route.fulfill({response}).catch(()=>{});});
const settled=()=>page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&Number(document.querySelector('.gf-score')?.dataset.mappedNotes)===430,{},{timeout:120000});
async function action(kind,perform){const pending=page.waitForResponse(r=>r.url().endsWith('/'+kind)&&r.request().method()==='POST',{timeout:300000});await perform();const response=await pending;assert.equal(response.status(),200,await response.text());const body=await response.json();await settled();return body;}
async function open(path){const pending=page.waitForResponse(r=>r.url().endsWith('/api/projects/open'));await page.getByLabel('打开工程',{exact:true}).setInputFiles(path);assert.equal((await pending).status(),200);await settled();}
async function save(path){const d=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();await(await d).saveAs(path);return JSON.parse(await fs.readFile(path,'utf8'));}
const report={};
try{
 await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
 await open('exports/AMT-呜-完整示例.acproject.json');await page.locator('.score-settings summary').click();
 assert.ok(await page.getByRole('button',{name:'生成所选器乐段',exact:true}).isDisabled());
 let h=await action('harmony',()=>page.getByRole('button',{name:'重新推导未锁定和弦',exact:true}).click());
 assert.equal(h.policy,'adaptive-block-v1');assert.equal(h.instrumentalSections.length,2);
 assert.ok(h.segments.some((s,i)=>i&&s.number===h.segments[i-1].number&&s.chordId!==h.segments[i-1].chordId));
 assert.ok(h.choices.some(c=>c.quality==='dim7'));assert.ok(h.choices.some(c=>c.quality==='maj7'));
 const chord=page.locator('.basic-harmony tr[data-harmony-measure]').filter({has:page.locator('select')}).filter({hasText:/C|Dm|Em|F|G|Am|B/}).first().locator('select');
 h=await action('harmony',()=>chord.selectOption('1:maj7'));assert.ok(Object.values(h.segmentLocks).includes('1:maj7'));
 h=await action('harmony',()=>page.getByRole('button',{name:'清除锁定',exact:true}).click());assert.deepEqual(h.segmentLocks,{});
 report.variableHarmony=true;report.segmentLocks=true;
 const first=h.instrumentalSections[0],second=h.instrumentalSections[1];
 await page.locator(`[data-section="${second.id}"] input[type="checkbox"]`).uncheck();
 await page.getByLabel(`器乐结束小节 ${first.id}`,{exact:true}).selectOption(String(first.firstMeasure+1));
 const fingerprint=await page.locator('.gf-score').getAttribute('data-playback-version');
 await page.getByRole('button',{name:'生成所选器乐段',exact:true}).click();await page.waitForResponse(r=>r.url().endsWith('/progress'));
 const cancellation=page.waitForResponse(r=>r.request().method()==='DELETE');await page.getByRole('button',{name:'取消生成',exact:true}).click();assert.equal((await cancellation).status(),204);
 assert.equal(await page.locator('.gf-score').getAttribute('data-playback-version'),fingerprint);report.cancelled=true;
 const take=await action('texture',()=>page.getByRole('button',{name:'生成所选器乐段',exact:true}).click());
 assert.equal(take.settings.mode,'hybrid-v1');assert.deepEqual(take.settings.sections,[{firstMeasure:first.firstMeasure,lastMeasure:first.firstMeasure+1}]);
 const fills=take.events.filter(e=>e.role==='instrumental'),blocks=take.events.filter(e=>e.role==='block');assert.ok(fills.length>0);
 const left=first.start,right=h.bars[first.firstMeasure].playEnd;
 assert.ok(fills.every(e=>left<=e.start&&e.end<=right+1e-7));
 for(const e of fills)assert.ok(opened.workspace.versions[opened.workspace.activeVersion].score.events.every(n=>n.start>=e.end||n.end<=e.start));
 assert.deepEqual(blocks.map(({role,voice,...e})=>e),h.events);
 assert.ok(progress.length>0);report.realApiGeneration=true;report.generatedEvents=fills.length;report.blockEvents=blocks.length;
 assert.equal(await page.locator('.gf-score').getAttribute('data-mapped-notes'),'430');
 assert.notEqual(await page.locator('.gf-score').getAttribute('data-notation-status'),'preserved');
 await page.getByRole('button',{name:'试听此段',exact:true}).first().click();await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');await page.getByRole('button',{name:'停止',exact:true}).click();
 const saved=await save('tests/output/hybrid-ui.acproject.json');assert.equal(saved.appVersion,'0.6.0');
 const expected=saved.textureSets;await open('tests/output/hybrid-ui.acproject.json');
 const again=await save('tests/output/hybrid-ui-reopened.acproject.json');assert.deepEqual(again.textureSets,expected);assert.deepEqual(again.source,saved.source);report.roundtrip=true;
 // Inspect the complete new example with both detected sections and both hands.
 await open('exports/柱式与器乐-呜-示例.acproject.json');
 report.fullPages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));report.mappedNotes=430;
 const rightNotes=page.locator('.score-note[data-staff="1"][data-voice="3"]');assert.ok(await rightNotes.count()>0);
 assert.equal(await rightNotes.locator('[data-note-id]').count(),0);report.generatedRightHandProtected=true;
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();await(await download).saveAs('tests/output/hybrid-page.png');
 await page.screenshot({path:'tests/output/hybrid-desktop.png'});await page.locator('.score-page:visible svg').screenshot({path:'tests/output/hybrid-score.png'});
 await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'工具',exact:true}).click();await page.locator('.score-settings summary').click();await page.locator('.accompaniment-panel').scrollIntoViewIfNeeded();
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));await page.screenshot({path:'tests/output/hybrid-mobile.png'});
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);report.errors=errors;report.warnings=warnings;
 await fs.writeFile('tests/output/hybrid-ui-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(error){await page.screenshot({path:'tests/output/hybrid-failure.png'}).catch(()=>{});console.log({errors,warnings});throw error;}finally{await browser.close();}
