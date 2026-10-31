// Historical UI scenario. See ../README.md for the maintained v0.7.2 suite.
import {chromium,browserPath,routeQaApi} from '../browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
await context.addInitScript(()=>{window.print=()=>{document.documentElement.dataset.printRequested='true';};});
const page=await context.newPage(),errors=[],warnings=[];page.setDefaultTimeout(60000);
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='warning'&&m.text().includes('Preserving source engraving'))warnings.push(m.text());});
await routeQaApi(page,process.env.QA_API_URL||'http://127.0.0.1:8770');
try{
 await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
 const opened=page.waitForResponse(r=>r.url().endsWith('/api/projects/open'));await page.getByLabel('打开工程',{exact:true}).setInputFiles('exports/柱式与器乐-呜-示例.acproject.json');const response=await opened;assert.equal(response.status(),200,await response.text());
 await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.rendering==='false'&&document.querySelector('.gf-score')?.dataset.mappedNotes==='430');
 const data=await response.json(),score=data.workspace.versions[data.workspace.activeVersion].score,take=Object.values(data.workspace.textureSets)[0].items[0];
 const expected=JSON.parse(await fs.readFile('exports/柱式与器乐-呜-示例.acproject.json','utf8'));
 assert.deepEqual(take.events,Object.values(expected.textureSets)[0].items[0].events);
 assert.equal(score.noteCount,430);assert.equal(await page.locator('.measure-hitbox').count(),82);
 const pages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));
 const generated=await page.locator('.score-note[data-staff="1"]').evaluateAll(ns=>ns.filter(n=>n.dataset.voice!=='1'&&!n.hasAttribute('data-note-id')).length);assert.ok(generated>0);
 const zip=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'导出全部页',exact:true}).click();await(await zip).saveAs('tests/output/hybrid-pages.zip');
 await page.locator('.export-options summary').click();const pending=page.waitForEvent('popup');await page.getByRole('button',{name:'打印 / 保存为 PDF',exact:true}).click();const popup=await pending;
 await popup.waitForFunction(()=>document.documentElement.dataset.printRequested==='true',{},{timeout:180000});assert.equal(await popup.locator('img').count(),pages);await popup.pdf({path:'tests/output/hybrid-print.pdf',preferCSSPageSize:true});await popup.close();
 await page.screenshot({path:'tests/output/hybrid-final-desktop.png'});await page.locator('.score-page:visible svg').screenshot({path:'tests/output/hybrid-final-score.png'});
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
 await fs.writeFile('tests/output/hybrid-export-checks.json',JSON.stringify({browser:await browser.version(),pages,originalNotes:430,measures:82,generatedRightHandElements:generated,zip:true,printPages:pages,eventsUnchanged:true,errors,warnings},null,2));console.log('Complete hybrid project, both staves, 430 IDs, ZIP and print passed:',pages,'pages');
}finally{await browser.close();}
