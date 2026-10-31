// Historical UI scenario. See ../README.md for the maintained v0.7.2 suite.
import {chromium,browserPath,routeQaApi} from '../browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const qa=process.env.QA_API_URL||'http://127.0.0.1:8770';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
await context.addInitScript(()=>{window.print=()=>{document.documentElement.dataset.printRequested='true';};});
const page=await context.newPage(),errors=[],warnings=[],progress=[];page.setDefaultTimeout(60000);let opened;
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='warning'&&m.text().includes('Preserving source engraving'))warnings.push(m.text());});
await routeQaApi(page,qa);
await page.route('**/api/projects/open',async route=>{const response=await route.fetch({url:qa+'/api/projects/open',headers:{...route.request().headers(),origin:'http://127.0.0.1:8765'},timeout:0});assert.equal(response.status(),200,await response.text());opened=await response.json();await route.fulfill({json:opened});});
page.on('response',async r=>{if(r.url().endsWith('/progress')){try{progress.push(await r.json());}catch{}}});
const settled=()=>page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&document.querySelector('.gf-score')?.dataset.mappedNotes==='430',{},{timeout:120000});
async function open(path){const p=page.waitForResponse(r=>r.url().endsWith('/api/projects/open'));await page.getByLabel('打开工程',{exact:true}).setInputFiles(path);assert.equal((await p).status(),200);await settled();}
async function save(path){const p=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();await(await p).saveAs(path);return JSON.parse(await fs.readFile(path,'utf8'));}
const report={};
try{
 await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
 await open('exports/情感器乐-呜-对照示例.acproject.json');await page.locator('.score-settings summary').click();
 assert.equal(await page.getByLabel('器乐生成模型',{exact:true}).inputValue(),'emo');assert.equal(await page.getByLabel('器乐情感方向',{exact:true}).inputValue(),'sad');assert.equal(await page.getByLabel('器乐张力走向',{exact:true}).inputValue(),'rising');
 const source=JSON.parse(await fs.readFile('exports/情感器乐-呜-对照示例.acproject.json','utf8'));
 const initial=await save('tests/output/emotion-initial.acproject.json');assert.deepEqual(initial.source,source.source);assert.deepEqual(initial.textureSets,source.textureSets);
 report.initialRoundtrip=true;report.initialPages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));
 assert.equal(await page.locator('.measure-hitbox').count(),82);
 for(const [index,engine] of [[1,'midi-emotion'],[0,'emo']]){
  await page.getByLabel('试听版本',{exact:true}).selectOption(String(index));await settled();assert.equal(await page.getByLabel('器乐生成模型',{exact:true}).inputValue(),engine);
  await page.getByRole('button',{name:'试听此段',exact:true}).first().click();await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');await page.getByRole('button',{name:'停止',exact:true}).click();
 }
 report.bothCandidatesPlayable=true;
 const first=page.locator('.instrumental-section').first(),second=page.locator('.instrumental-section').nth(1);await second.locator('input[type="checkbox"]').uncheck();
 const owner=opened.workspace.versions[opened.workspace.activeVersion].harmony.instrumentalSections[0];await first.locator('select').nth(1).selectOption(String(owner.firstMeasure+1));
 const before=await page.locator('.gf-score').getAttribute('data-playback-version');await page.getByRole('button',{name:'生成所选器乐段',exact:true}).click();await page.waitForResponse(r=>r.url().endsWith('/progress'));
 const deleted=page.waitForResponse(r=>r.request().method()==='DELETE');await page.getByRole('button',{name:'取消生成',exact:true}).click();assert.equal((await deleted).status(),204);assert.equal(await page.locator('.gf-score').getAttribute('data-playback-version'),before);report.cancelled=true;
 await page.getByLabel('器乐生成模型',{exact:true}).selectOption('midi-emotion');await page.getByLabel('器乐情感方向',{exact:true}).selectOption('tense');await page.getByLabel('器乐张力走向',{exact:true}).selectOption('falling');
 const pending=page.waitForResponse(r=>r.url().endsWith('/texture')&&r.request().method()==='POST',{timeout:240000});await page.getByRole('button',{name:'生成所选器乐段',exact:true}).click();const response=await pending;assert.equal(response.status(),200,await response.text());const take=await response.json();await settled();
 assert.equal(take.settings.mode,'hybrid-v2');assert.deepEqual(take.settings.emotion,{engine:'midi-emotion',feeling:'tense',contour:'falling'});
 const fills=take.events.filter(e=>e.role==='instrumental');assert.ok(fills.length>0);assert.ok(new Set(fills.map(e=>e.velocity)).size>1);
 const bars=opened.workspace.versions[opened.workspace.activeVersion].harmony.bars,right=bars[owner.firstMeasure].playEnd;
 assert.ok(fills.every(e=>e.start>=owner.start&&e.end<=right+1e-7));report.realApiEmotionGeneration=true;report.generatedEvents=fills.length;
 const saved=await save('tests/output/emotion-workspace.acproject.json');await open('tests/output/emotion-workspace.acproject.json');const reopened=await save('tests/output/emotion-reopened.acproject.json');assert.deepEqual(saved.textureSets,reopened.textureSets);assert.deepEqual(saved.source,reopened.source);report.generatedRoundtrip=true;
 // Export the original EMO candidate; all outputs share the final engraving.
 await page.locator('.score-settings summary').click();await page.getByLabel('试听版本',{exact:true}).selectOption('0');await settled();assert.equal(await page.locator('.instrumental-section').nth(1).locator('input').isChecked(),true);const pages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));
 const png=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();await(await png).saveAs('tests/output/emotion-page.png');
 const zip=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'导出全部页',exact:true}).click();await(await zip).saveAs('tests/output/emotion-pages.zip');
 await page.locator('.export-options summary').click();const popupPending=page.waitForEvent('popup');await page.getByRole('button',{name:'打印 / 保存为 PDF',exact:true}).click();const popup=await popupPending;await popup.waitForFunction(()=>document.documentElement.dataset.printRequested==='true',{},{timeout:180000});assert.equal(await popup.locator('img').count(),pages);await popup.pdf({path:'tests/output/emotion-print.pdf',preferCSSPageSize:true});await popup.close();
 await page.screenshot({path:'tests/output/emotion-desktop.png'});await page.locator('.score-page:visible svg').screenshot({path:'tests/output/emotion-score.png'});
 await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'工具',exact:true}).click();await page.locator('.emotion-controls').scrollIntoViewIfNeeded();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));await page.screenshot({path:'tests/output/emotion-mobile.png'});
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);Object.assign(report,{pages,printPages:pages,progressUpdates:progress.length,errors,warnings});await fs.writeFile('tests/output/emotion-ui-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(e){console.log({errors,warnings});await page.screenshot({path:'tests/output/emotion-ui-failure.png'}).catch(()=>{});throw e;}finally{await browser.close();}
