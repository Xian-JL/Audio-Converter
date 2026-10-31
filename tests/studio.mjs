// v0.7.2 task flow, persistence and full-page layout against an isolated QA service.
import {chromium,browserPath,routeQaApi} from './browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const fixture='exports/EMO-呜-乐句发展示例.acproject.json';
const original=JSON.parse(await fs.readFile(fixture,'utf8'));
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
await context.addInitScript(()=>{window.print=()=>{document.documentElement.dataset.printRequested='true';};});
const page=await context.newPage(),errors=[],warnings=[],report={};
page.setDefaultTimeout(60000);
page.on('pageerror',error=>errors.push(error.message));
page.on('console',message=>{if(message.type()==='warning'&&message.text().includes('Preserving source engraving'))warnings.push(message.text());});
await routeQaApi(page,process.env.QA_API_URL||'http://127.0.0.1:8770');
const settled=()=>page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&document.querySelector('.gf-score')?.dataset.mappedNotes==='430',{},{timeout:120000});
const task=name=>page.getByRole('tab',{name,exact:true}).click();
async function save(name){const pending=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();await(await pending).saveAs(name);return JSON.parse(await fs.readFile(name,'utf8'));}
async function noOverflow(){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));}
try{
  await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
  assert.equal(await page.locator('.release-tag').textContent(),'v0.7.2');
  await page.screenshot({path:'tests/output/studio-start.png'});
  await page.getByLabel('打开工程',{exact:true}).setInputFiles(fixture);await settled();
  assert.equal(await page.locator('.measure-hitbox').count(),82);
  assert.equal(await page.getByRole('tab',{name:'器乐',exact:true}).getAttribute('aria-selected'),'true');
  assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'2');
  // Every tab has one visible panel and supports arrow/Home/End keyboard navigation.
  for(const name of ['旋律','和弦','器乐','演奏','导出']){
    await task(name);assert.equal(await page.locator('.tool-task:visible').count(),1);
    assert.ok(await page.getByRole('button',{name:'保存工程',exact:true}).isVisible());
  }
  await page.getByRole('tab',{name:'导出',exact:true}).press('Home');
  assert.equal(await page.getByRole('tab',{name:'旋律',exact:true}).getAttribute('aria-selected'),'true');
  await page.getByRole('tab',{name:'旋律',exact:true}).press('ArrowRight');
  assert.equal(await page.getByRole('tab',{name:'和弦',exact:true}).getAttribute('aria-selected'),'true');
  report.keyboardAndPanels=true;
  await task('器乐');await page.getByLabel('器乐情感方向',{exact:true}).selectOption('calm');
  await task('演奏');await task('器乐');assert.equal(await page.getByLabel('器乐情感方向',{exact:true}).inputValue(),'calm');
  // Draft settings must not overwrite the saved selected candidate.
  const saved=await save('tests/output/studio-roundtrip.acproject.json');
  assert.equal(saved.appVersion,'0.7.2');assert.deepEqual(saved.source,original.source);
  assert.deepEqual(saved.textureSets,original.textureSets);assert.deepEqual(saved.versions,original.versions.map((v,i)=>({...v,kind:i===0?'original':v.kind==='edit'?'edit':'rebar',harmony:v.harmony||null})));
  report.exactRoundtrip=true;report.draftsSurviveTabs=true;
  for(const index of ['0','2']){
    await page.getByLabel('试听版本',{exact:true}).selectOption(index);await settled();
    await page.getByRole('button',{name:'试听此段',exact:true}).nth(1).click();
    await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');
    await page.getByRole('button',{name:'停止',exact:true}).click();
  }
  report.oldAndAcceptedPlayable=true;
  await page.screenshot({path:'tests/output/studio-desktop.png'});
  for(const [width,height] of [[390,844],[390,667],[1024,768],[1920,1080]]){
    await page.setViewportSize({width,height});await page.waitForTimeout(200);await noOverflow();
    if(width<1200){
      for(const name of ['音频','工具','乐谱']){await task(name);await noOverflow();}
      await task('工具');await task('器乐');
      await page.locator('.emotion-controls').scrollIntoViewIfNeeded();await noOverflow();
      if(height===844)await page.screenshot({path:'tests/output/studio-mobile.png'});
      await task('乐谱');
      if(height===844)await page.screenshot({path:'tests/output/studio-mobile-score.png'});
    }
  }
  report.responsive=true;await page.setViewportSize({width:1440,height:900});
  await task('演奏');await page.locator('.navigation-settings summary').click();
  await page.getByLabel('页面密度',{exact:true}).selectOption('standard');await settled();
  await page.getByLabel('页面密度',{exact:true}).selectOption('compact');await settled();
  const pages=Number(await page.locator('.gf-score').getAttribute('data-page-count'));
  await task('导出');
  let pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();
  await(await pending).saveAs('tests/output/studio-page.png');
  const png=await fs.readFile('tests/output/studio-page.png');assert.equal(png.readUInt32BE(16),2480);assert.equal(png.readUInt32BE(20),3508);
  pending=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'导出全部页',exact:true}).click();await(await pending).saveAs('tests/output/studio-pages.zip');
  await page.locator('.export-options summary').click();
  const popupPending=page.waitForEvent('popup');await page.getByRole('button',{name:'打印 / 保存为 PDF',exact:true}).click();
  const popup=await popupPending;await popup.waitForFunction(()=>document.documentElement.dataset.printRequested==='true',{},{timeout:180000});
  assert.equal(await popup.locator('img').count(),pages);await popup.close();
  report.exports={pages,png:[2480,3508],zip:true,print:true};
  // A real generation continues while the user inspects another task.
  await task('器乐');await page.locator('.instrumental-section').first().locator('input[type=checkbox]').uncheck();
  const generated=page.waitForResponse(r=>r.url().endsWith('/texture')&&r.request().method()==='POST',{timeout:240000});
  await page.getByRole('button',{name:'生成所选器乐段',exact:true}).click();await task('演奏');
  const response=await generated;assert.equal(response.status(),200,await response.text());const take=await response.json();
  assert.equal(take.model.development,'phrase-development-v1');await settled();await task('器乐');
  assert.equal(await page.getByLabel('试听版本',{exact:true}).inputValue(),'3');
  report.generationSurvivesTabs=true;
  await page.getByLabel('打开工程',{exact:true}).setInputFiles('tests/output/studio-roundtrip.acproject.json');await settled();
  const reopened=await save('tests/output/studio-reopened.acproject.json');assert.deepEqual(reopened.source,original.source);assert.deepEqual(reopened.textureSets,original.textureSets);
  assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);Object.assign(report,{mappedNotes:430,measures:82,errors,warnings});
  await fs.writeFile('tests/output/studio-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(error){await page.screenshot({path:'tests/output/studio-failure.png'}).catch(()=>{});console.log({errors,warnings});throw error;}
finally{await browser.close();}
