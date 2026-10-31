// Historical UI scenario. See ../README.md for the maintained v0.7.2 suite.
import {chromium,browserPath,routeQaApi} from '../browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const qa=process.env.QA_API_URL||'http://127.0.0.1:8770',path='exports/EMO-呜-乐句发展示例.acproject.json';
const payload=JSON.parse(await fs.readFile(path,'utf8')),set=Object.values(payload.textureSets)[0],selected=set.items[set.active];
const original=JSON.parse(payload.source.identityNotesJson).map(n=>({id:n.id,start:n.start,end:n.end,pitches:[n.midi],staff:1}));
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
await context.addInitScript(()=>{window.print=()=>{document.documentElement.dataset.printRequested='true';};});
const page=await context.newPage(),errors=[],warnings=[];page.setDefaultTimeout(60000);
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='warning'&&m.text().includes('Preserving source engraving'))warnings.push(m.text());});
await routeQaApi(page,qa);
await page.route('**/api/jobs/*/texture',async route=>{const body=route.request().postDataJSON();body.seed=20261030;const headers={...route.request().headers(),origin:'http://127.0.0.1:8765'};delete headers['content-length'];const response=await route.fetch({url:qa+new URL(route.request().url()).pathname,headers,postData:JSON.stringify(body),timeout:0});await route.fulfill({response});});
const settled=()=>page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&document.querySelector('.gf-score')?.dataset.mappedNotes==='430',{},{timeout:120000});
async function save(file){const event=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();await(await event).saveAs(file);return JSON.parse(await fs.readFile(file,'utf8'));}
const report={};
try{
 await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
 await page.getByLabel('打开工程',{exact:true}).setInputFiles(path);await settled();await page.locator('.score-settings summary').click();
 assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'2');assert.ok((await page.getByLabel('试听版本',{exact:true}).locator('option:checked').textContent()).includes('乐句发展'));
 assert.equal(await page.locator('.measure-hitbox').count(),82);assert.equal(await page.getByLabel('器乐情感方向',{exact:true}).inputValue(),'sad');assert.equal(await page.getByLabel('器乐张力走向',{exact:true}).inputValue(),'rising');
 for(const index of ['0','2']){
  await page.getByLabel('试听版本',{exact:true}).selectOption(index);await settled();await page.getByRole('button',{name:'试听此段',exact:true}).nth(1).click();await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');await page.getByRole('button',{name:'停止',exact:true}).click();
 }
 const snapshot=await save('tests/output/phrase-roundtrip.acproject.json');assert.deepEqual(snapshot.textureSets,payload.textureSets);assert.deepEqual(snapshot.source,payload.source);report.oldAndNewPlayable=true;report.roundtrip=true;
 const pages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));
 const png=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();await(await png).saveAs('tests/output/phrase-page.png');
 const zip=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'导出全部页',exact:true}).click();await(await zip).saveAs('tests/output/phrase-pages.zip');
 await page.locator('.export-options summary').click();const popupEvent=page.waitForEvent('popup');await page.getByRole('button',{name:'打印 / 保存为 PDF',exact:true}).click();const popup=await popupEvent;await popup.waitForFunction(()=>document.documentElement.dataset.printRequested==='true',{},{timeout:180000});assert.equal(await popup.locator('img').count(),pages);await popup.close();
 await page.screenshot({path:'tests/output/phrase-desktop.png'});await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'工具',exact:true}).click();await page.locator('.emotion-controls').scrollIntoViewIfNeeded();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));await page.screenshot({path:'tests/output/phrase-mobile.png'});await page.setViewportSize({width:1440,height:900});
 // Real worker generation on the same interlude, using a reproducible seed.
 await page.locator('.instrumental-section').first().locator('input[type="checkbox"]').uncheck();
 const event=page.waitForResponse(r=>r.url().endsWith('/texture')&&r.request().method()==='POST',{timeout:240000});await page.getByRole('button',{name:'生成所选器乐段',exact:true}).click();const response=await event;assert.equal(response.status(),200,await response.text());const take=await response.json();await settled();
 assert.equal(take.model.development,'phrase-development-v1');const notes=take.events.filter(e=>e.role==='instrumental');assert.equal(new Set(notes.flatMap(e=>e.pitches.map(p=>e.start+':'+p))).size,notes.reduce((n,e)=>n+e.pitches.length,0));report.realWorkerGeneration=true;
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);Object.assign(report,{pages,mappedNotes:430,measures:82,errors,warnings});await fs.writeFile('tests/output/phrase-ui-checks.json',JSON.stringify(report,null,2));
 const audioPage=await context.newPage();await audioPage.route('**/api/**',r=>r.fulfill({status:200,json:{ready:true,engine:'game',scoreVersion:20}}));await audioPage.goto('http://127.0.0.1:5173');
 const region=selected.references.find(r=>r.kind==='interlude'),left=region.start-6,right=region.end+6;
 const audio=await audioPage.evaluate(async({events,left,right})=>{const harness=await import('/tests/emotion-audio.ts');return harness.render(events,left,right);},{events:[...original,...selected.events],left,right});assert.ok(audio.rms>1e-6&&audio.peak<1);
 await fs.writeFile('exports/EMO-呜-间奏乐句发展试听.wav',Buffer.from(audio.wav,'base64'));await fs.writeFile('tests/output/phrase-audio-checks.json',JSON.stringify({peak:audio.peak,rms:audio.rms,seconds:audio.seconds,left,right,samePiano:true,levels:[60,40]},null,2));console.log(JSON.stringify(report,null,2));
}catch(e){await page.screenshot({path:'tests/output/phrase-ui-failure.png'}).catch(()=>{});console.log({errors,warnings});throw e;}finally{await browser.close();}
