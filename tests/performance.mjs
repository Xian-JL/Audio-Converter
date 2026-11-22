import {chromium,browserPath} from './browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true}),errors=[];
page.setDefaultTimeout(90000);page.on('pageerror',e=>errors.push(e.message));
// Serve the isolated QA API and UI together on 8765. Browser multipart uploads
// must reach Flask directly; Playwright request forwarding can lose file bytes.
const origin='http://127.0.0.1:8765';
const task=name=>page.getByRole('tab',{name,exact:true}).click();
const settled=(count)=>page.waitForFunction(count=>!document.querySelector('.project-actions button')?.disabled&&!document.querySelector('.recording-kind select')?.disabled&&document.querySelector('.gf-score')?.dataset.rendering==='false'&&Number(document.querySelector('.gf-score')?.dataset.pageCount)>0&&(count===undefined||Number(document.querySelector('.gf-score')?.dataset.mappedNotes)===count),count);
async function action(path,fn){const response=page.waitForResponse(r=>r.url().endsWith('/'+path)&&r.request().method()==='POST');await fn();const r=await response;assert.equal(r.status(),200,await r.text());const payload=await r.json();if(payload.score)await page.waitForFunction(fp=>document.querySelector('.gf-score')?.dataset.scoreFingerprint===fp,payload.score.scoreFingerprint);return payload;}
async function save(name){const pending=page.waitForEvent('download');await page.getByRole('button',{name:'保存工程',exact:true}).click();await(await pending).saveAs(name);return JSON.parse(await fs.readFile(name,'utf8'));}
const report={};
try{
 await page.goto(origin);await page.getByRole('button',{name:'中文',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);
 await page.getByLabel('打开工程',{exact:true}).setInputFiles('tests/fixtures/performance-project.json');await settled(4);
 assert.ok(await page.getByRole('tab',{name:'和弦',exact:true}).isDisabled());
 assert.equal(await page.locator('.score-note[data-note-id="c"][data-anchor-onset=true]').count(),1);assert.equal(await page.locator('.score-note[data-note-id="e"][data-anchor-onset=true]').count(),1);
 await page.getByRole('button',{name:'编辑音符',exact:true}).click();
 await page.locator('.score-note[data-note-id="e"][data-anchor-onset=true] .score-hitbox').click();
 await page.waitForFunction(()=>document.querySelector('input[aria-label="音高 MIDI"]')?.value==='64');
 await page.getByLabel('音高 MIDI',{exact:true}).fill('65');await page.getByLabel('音符谱表',{exact:true}).selectOption('2');
 const edited=await action('edit',()=>page.getByRole('button',{name:'应用修改',exact:true}).click());await settled(4);
 assert.equal(edited.score.notes.find(n=>n.id==='e').staff,2);assert.equal(edited.score.notes.find(n=>n.id==='c').midi,60);report.chordMembersIndependent=true;
 await page.getByRole('button',{name:'结束校对',exact:true}).click();await page.getByRole('button',{name:'撤销',exact:true}).click();await settled(4);
 await page.getByRole('button',{name:'定位小节第一拍',exact:true}).click();await page.locator('.score-note[data-note-id="repeat"][data-anchor-onset=true] .score-hitbox').click();
 const rebuilt=await action('rebar',()=>page.getByRole('button',{name:'重构乐谱',exact:true}).click());await settled(4);assert.equal(rebuilt.score.downbeat.noteId,'repeat');
 assert.equal(rebuilt.score.events.find(n=>n.id==='repeat').start,.5);report.rebarPreservesPerformance=true;
 const snapshot=await save('tests/output/performance-roundtrip.acproject.json');assert.equal(snapshot.schemaVersion,3);assert.equal(snapshot.source.sourceKind,'piano');assert.equal(snapshot.versions.length,3);
 await task('导出');
 let pending=page.waitForEvent('download');await page.getByRole('button',{name:'演奏谱 MIDI',exact:true}).click();await(await pending).saveAs('tests/output/performance-export.mid');assert.equal((await fs.readFile('tests/output/performance-export.mid')).subarray(0,4).toString(),'MThd');
 pending=page.waitForEvent('download');await page.getByRole('button',{name:'当前谱 MusicXML',exact:true}).click();await(await pending).saveAs('tests/output/performance-export.musicxml');
 pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载此页 PNG',exact:true}).click();await(await pending).saveAs('tests/output/performance-page.png');report.exports=true;
 await task('旋律');await action('melody-branch',()=>page.getByRole('button',{name:'建立主旋律候选',exact:true}).click());await settled();
 assert.ok(await page.getByRole('tab',{name:'和弦',exact:true}).isDisabled());await page.getByRole('button',{name:'已核对主旋律，开放编配',exact:true}).click();await task('和弦');
 await action('harmony',()=>page.getByRole('button',{name:'生成柱式和弦',exact:true}).click());await settled();report.confirmedMelodyBranch=true;
 const branch=await save('tests/output/performance-branch.acproject.json');assert.equal(branch.versions.at(-1).scoreMode,'melody');assert.ok(branch.versions.at(-1).melodyConfirmed);
 await page.getByLabel('打开工程',{exact:true}).setInputFiles('tests/output/performance-branch.acproject.json');await page.waitForFunction(()=>!document.querySelector('.project-actions button')?.disabled);await settled();
 const reopened=await save('tests/output/performance-reopened.acproject.json');assert.deepEqual(reopened.source,branch.source);assert.deepEqual(reopened.versions,branch.versions);report.exactRoundtrip=true;
 await page.screenshot({path:'tests/output/performance-desktop.png'});
 await page.setViewportSize({width:390,height:844});await task('工具');await task('旋律');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'tests/output/performance-mobile.png'});report.mobile=true;
 await page.setViewportSize({width:1440,height:900});
 if(await fs.stat('tests/output/instrument-piano-probe.flac').catch(()=>null)&&await fs.stat('tests/output/guzheng-real-30s.flac').catch(()=>null)){
 // Actual raw file import: instrument jobs bypass separation and invoke the pinned model.
 const parameters=async()=>{await page.getByLabel('速度（BPM）',{exact:true}).fill('120');await page.getByLabel('拍号',{exact:true}).selectOption('4/4');await page.getByLabel('调',{exact:true}).selectOption('C major');await page.getByRole('button',{name:'应用乐谱参数',exact:true}).click();};
 await page.getByText('打开或替换',{exact:true}).click();
 await page.getByLabel('录音类型',{exact:true}).selectOption('piano');
 let upload=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
 await page.locator('input[accept*="audio/mpeg"]').setInputFiles('tests/output/instrument-piano-probe.flac');assert.equal((await upload).status(),202);await parameters();await settled();assert.ok(Number(await page.locator('.gf-score').getAttribute('data-mapped-notes'))>0);report.actualPianoImport=true;
 await save('tests/output/performance-piano.acproject.json');await page.getByText('打开或替换',{exact:true}).click();await page.getByLabel('录音类型',{exact:true}).selectOption('guzheng');upload=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('input[accept*="audio/mpeg"]').setInputFiles('tests/output/guzheng-real-30s.flac');assert.equal((await upload).status(),202);await parameters();await settled();
 assert.ok(await page.getByRole('button',{name:'建立官方解码基线对照',exact:true}).isVisible());await action('transcription-candidate',()=>page.getByRole('button',{name:'建立官方解码基线对照',exact:true}).click());await settled();report.actualGuzhengAndBaseline=true;
 const g=await save('tests/output/performance-guzheng.acproject.json');assert.equal(g.source.sourceKind,'guzheng');assert.ok(g.source.baselineNotes.length>0);
 }else report.actualImportsSkipped='Prepare local probe recordings; see tests/README.md';
 assert.deepEqual(errors,[]);report.errors=errors;await fs.writeFile('tests/output/performance-ui-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(error){await page.screenshot({path:'tests/output/performance-failure.png'}).catch(()=>{});throw error;}finally{await browser.close();}
