import {chromium,browserPath,routeQaApi} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const qa=process.env.QA_API_URL||'http://127.0.0.1:8770';
const sourcePath='exports/AMT-呜-完整示例.acproject.json';
const saved=JSON.parse(await fs.readFile(sourcePath,'utf8'));
await fs.mkdir('tests/output',{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
await context.addInitScript(()=>{window.print=()=>{document.documentElement.dataset.printRequested='true';};});
const page=await context.newPage(),errors=[],warnings=[];let opened;
page.setDefaultTimeout(60000);
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='warning'&&m.text().includes('Preserving source engraving'))warnings.push(m.text());});
await routeQaApi(page,qa);
await page.route('**/api/projects/open',async route=>{
  const response=await route.fetch({url:qa+'/api/projects/open',headers:{...route.request().headers(),origin:'http://127.0.0.1:8765'},timeout:0});
  assert.equal(response.status(),200,await response.text());opened=await response.json();
  // A padded QA audio fixture tests the source transport; no original song is copied or decoded.
  await route.fulfill({json:{...opened,job:{...opened.job,playbackReady:true}}});
});
await page.route('**/api/jobs/*/audio',async route=>{
  const response=await route.fetch({url:qa+'/api/jobs/'+'f'.repeat(32)+'/audio',timeout:0});await route.fulfill({response});
});
await page.route('**/api/jobs/*/texture',route=>{throw Error('Notation regression must not run AMT inference: '+route.request().url());});
const settle=()=>page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&Number(document.querySelector('.gf-score')?.dataset.pageCount)>0,{},{timeout:120000});
const task=async name=>page.getByRole('tab',{name,exact:true}).click();
const navigation=async()=>{await task('演奏');if(!await page.locator('.navigation-settings').evaluate(e=>e.open))await page.locator('.navigation-settings summary').click();};
async function choose(id) {
  await navigation();const n=page.locator(`.score-note[data-note-id="${id}"][data-anchor-onset="true"]`).first();
  assert.equal(await n.count(),1,'Missing real onset '+id);
  await page.getByLabel('乐谱页码',{exact:true}).selectOption(await n.getAttribute('data-page'));await task('旋律');await n.locator('.score-hitbox').click();
}
async function save(name) {
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();
  await(await pending).saveAs(name);return JSON.parse(await fs.readFile(name,'utf8'));
}
async function download(button,name) {
  const pending=page.waitForEvent('download',{timeout:180000});await button.click();const file=await pending;await file.saveAs(name);return file.suggestedFilename();
}
const report={};
try {
  await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'中文',exact:true}).click();
  await page.getByRole('button',{name:'打开工程',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
  await page.getByLabel('打开工程',{exact:true}).setInputFiles(sourcePath);await settle();
  const active=opened.workspace.versions[opened.workspace.activeVersion].score;
  const texture=Object.values(opened.workspace.textureSets)[0].items[0];
  report.beforeNoteElements=(texture.xml.match(/<note[ >]/g)||[]).length;
  const state=await page.locator('.gf-score').evaluate(n=>({...n.dataset}));
  assert.equal(state.notationVersion,'equivalent-v1');assert.equal(state.notationStatus,'simplified');
  assert.ok(Number(state.notationRemovedFragments)>0);assert.equal(state.mappedNotes,'430');
  report.removedFragments=Number(state.notationRemovedFragments);report.afterNoteElements=report.beforeNoteElements-report.removedFragments;
  const pages=Number(state.pageCount);report.pages=pages;
  const mapping=await page.locator('.measure-hitbox').evaluateAll(ns=>ns.map(n=>({measure:Number(n.dataset.measure),page:Number(n.dataset.page)})));
  assert.equal(mapping.length,82);assert.equal(new Set(mapping.map(n=>n.measure)).size,82);
  assert.equal(await page.locator('.score-note[data-anchor-onset="true"]').evaluateAll(ns=>new Set(ns.map(n=>n.dataset.noteId)).size),430);
  report.allMelodyOnsets=true;report.measures=mapping.length;
  const untouched=await save('tests/output/notation-untouched.acproject.json');
  const normalizedVersions=saved.versions.map((v,i)=>({...v,kind:i===0?'original':v.kind==='edit'?'edit':'rebar',harmony:v.harmony||null}));
  assert.deepEqual(untouched.source,saved.source);assert.deepEqual(untouched.versions,normalizedVersions);assert.deepEqual(untouched.textureSets,saved.textureSets);
  report.originalDataUnchanged=true;
  // Switch the selected accompaniment both ways; derived XML is recalculated each time.
  await task('器乐');await page.getByLabel('试听版本',{exact:true}).selectOption('-1');await settle();
  assert.equal(await page.locator('.gf-score').getAttribute('data-playback-version'),opened.workspace.versions[opened.workspace.activeVersion].harmony.fingerprint);
  await page.getByLabel('试听版本',{exact:true}).selectOption('0');await settle();
  assert.equal(await page.locator('.gf-score').getAttribute('data-notation-removed-fragments'),state.notationRemovedFragments);
  await task('旋律');
  report.switchingRecomputed=true;
  // Both densities retain all IDs and the same performance identity.
  await navigation();await page.getByLabel('页面密度',{exact:true}).selectOption('standard');await settle();
  assert.equal(await page.locator('.gf-score').getAttribute('data-mapped-notes'),'430');
  await page.getByLabel('页面密度',{exact:true}).selectOption('compact');await settle();
  assert.equal(Number(await page.locator('.gf-score').getAttribute('data-page-count')),pages);
  // Pick notes across all parts of the piece, then rebuild with real API and unchanged events.
  await task('旋律');await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();
  const indexes=[0,90,190,290,400];
  for(const i of indexes) if(i!==0) await choose(active.notes[i].id);
  assert.equal(await page.locator('.downbeat-point').count(),5);
  const rebuild=page.waitForResponse(r=>r.url().endsWith('/rebar'));
  await page.getByRole('button',{name:'重构乐谱',exact:true}).click();const response=await rebuild;
  assert.equal(response.status(),200,await response.text());const reconstructed=await response.json();await settle();
  assert.equal(reconstructed.score.downbeats.length,5);assert.deepEqual(reconstructed.score.events,active.events);
  assert.equal(await page.locator('.gf-score').getAttribute('data-mapped-notes'),'430');
  assert.notEqual(await page.locator('.gf-score').getAttribute('data-notation-status'),'preserved');
  await page.getByLabel('查看版本',{exact:true}).selectOption(String(saved.activeVersion));await settle();
  report.fivePointRebuild=true;
  // Editing a surviving derived symbol still targets the original logical note.
  const editNote=active.notes[120];await page.getByRole('button',{name:'编辑旋律',exact:true}).click();await choose(editNote.id);
  assert.equal(Number(await page.getByLabel('起音（秒）',{exact:true}).inputValue()),editNote.start);
  await page.getByLabel('音高 MIDI',{exact:true}).fill(String(editNote.midi+1));
  const edit=page.waitForResponse(r=>r.url().endsWith('/edit'));await page.getByRole('button',{name:'应用修改',exact:true}).click();
  const edited=await(await edit).json();await settle();assert.equal(edited.score.notes.find(n=>n.id===editNote.id).midi,editNote.midi+1);
  assert.equal(await page.locator('.gf-score').getAttribute('data-mapped-notes'),'430');
  await page.getByRole('button',{name:'结束编辑',exact:true}).click();await page.getByLabel('查看版本',{exact:true}).selectOption(String(saved.activeVersion));await settle();report.editingMapped=true;
  // Loop, click outside the loop, then score and source transports cross a page boundary.
  await navigation();await page.getByLabel('循环起始小节',{exact:true}).selectOption('6');await page.getByLabel('循环结束小节',{exact:true}).selectOption('6');await page.getByLabel('循环播放',{exact:true}).check();
  await page.getByLabel('小节 / 时间',{exact:true}).selectOption('6');await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');
  const bar=opened.workspace.versions[saved.activeVersion].harmony.bars[5];
  await page.waitForTimeout((bar.playEnd-bar.playStart+1)*1000);
  assert.equal(await page.locator('.gf-score').getAttribute('data-current-measure'),'6');
  await page.getByRole('button',{name:'暂停',exact:true}).click();await page.getByLabel('乐谱页码',{exact:true}).selectOption('2');
  await page.locator('.score-page:visible .score-note').first().click();await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.playing==='true');
  assert.equal(await page.locator('.gf-score').getAttribute('data-looping'),'false');await page.getByRole('button',{name:'停止',exact:true}).click();
  const boundary=mapping.find(m=>m.page===2),timeline=opened.workspace.versions[saved.activeVersion].harmony.bars;
  const at=timeline[boundary.measure-1].playStart;
  await page.getByLabel('播放位置',{exact:true}).fill(String(at-.2));await page.getByRole('button',{name:'播放乐谱',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.currentPage==='2');await page.getByRole('button',{name:'停止',exact:true}).click();
  await page.locator('.player-card audio').evaluate(async(audio,at)=>{audio.currentTime=at;await audio.play();},at-.2);
  await page.waitForFunction(at=>document.querySelector('.player-card audio').currentTime>=at&&document.querySelector('.gf-score')?.dataset.currentPage==='2',at);
  await page.locator('.player-card audio').evaluate(a=>a.pause());report.loopAndBothTransports=true;
  // Clean rendered SVG is the shared source for PNG, both ZIP modes and print.
  await page.getByLabel('乐谱页码',{exact:true}).selectOption('2');
  await task('导出');report.png=await download(page.getByRole('button',{name:'下载此页 PNG',exact:true}),'tests/output/notation-page-2.png');
  const png=await fs.readFile('tests/output/notation-page-2.png');assert.equal(png.readUInt32BE(16),2480);assert.equal(png.readUInt32BE(20),3508);
  report.zip=await download(page.getByRole('button',{name:'导出全部页',exact:true}),'tests/output/notation-pages.zip');
  await page.locator('.export-options summary').click();await page.getByLabel('从页',{exact:true}).fill('2');await page.getByLabel('到页',{exact:true}).fill('3');
  await download(page.getByRole('button',{name:'导出页码范围',exact:true}),'tests/output/notation-range.zip');
  const popupPending=page.waitForEvent('popup');await page.getByRole('button',{name:'打印 / 保存为 PDF',exact:true}).click();const popup=await popupPending;
  await popup.waitForFunction(()=>document.documentElement.dataset.printRequested==='true',{},{timeout:180000});
  assert.equal(await popup.locator('img').count(),pages);await popup.pdf({path:'tests/output/notation-print.pdf',preferCSSPageSize:true,printBackground:true});await popup.close();report.printPages=pages;
  // Full project roundtrip after adding edit/rebuild versions; selected original AMT stays exact.
  const roundtrip=await save('tests/output/notation-workspace.acproject.json');
  assert.deepEqual(roundtrip.textureSets,saved.textureSets);assert.deepEqual(roundtrip.source,saved.source);
  await page.getByLabel('打开工程',{exact:true}).setInputFiles('tests/output/notation-workspace.acproject.json');await settle();
  const reopened=await save('tests/output/notation-reopened.acproject.json');assert.deepEqual(reopened.versions,roundtrip.versions);assert.deepEqual(reopened.textureSets,roundtrip.textureSets);
  assert.equal(await page.locator('.gf-score').getAttribute('data-mapped-notes'),'430');report.roundtrip=true;
  await page.screenshot({path:'tests/output/notation-desktop.png'});await page.locator('.score-page:visible svg').screenshot({path:'tests/output/notation-score.png'});
  for(const [width,height] of [[390,844],[390,667],[1920,1080]]) {
    await page.setViewportSize({width,height});await page.waitForTimeout(180);
    assert.equal(Number(await page.locator('.gf-score').getAttribute('data-page-count')),pages);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));
    if(width===390&&height===844)await page.screenshot({path:'tests/output/notation-mobile.png'});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);report.errors=errors;report.warnings=warnings;
  await fs.writeFile('tests/output/notation-ui-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(error){await page.screenshot({path:'tests/output/notation-ui-failure.png'}).catch(()=>{});console.log('Warnings',warnings);console.log('State',await page.locator('.gf-score').evaluate(n=>({...n.dataset})).catch(()=>null));throw error;}
finally{await browser.close();}
