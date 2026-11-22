import {chromium,browserPath} from './browser-runtime.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const page=await browser.newPage({viewport:{width:1280,height:720},acceptDownloads:true});
page.setDefaultTimeout(20000);
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
const origin='http://127.0.0.1:8765';
const fixture='tests/fixtures/performance-project.json';
const score=page.locator('.gf-score');
const button=name=>page.getByRole('button',{name,exact:true});
const ready=()=>page.waitForFunction(()=>document.querySelector('.gf-score[data-rendering="false"][data-mapped-notes="4"]'));
const fingerprint=()=>score.getAttribute('data-score-fingerprint');
const open=path=>page.getByLabel('打开工程',{exact:true}).setInputFiles(path);
const report={};
async function save(path){
  const download=page.waitForEvent('download');
  await button('保存工程').click();
  await (await download).saveAs(path);
  return JSON.parse(await fs.readFile(path,'utf8'));
}
try{
  await fs.mkdir('tests/output',{recursive:true});
  await page.goto(origin);
  await button('中文').click();
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
  await button('选择音频').waitFor();
  assert.equal(await page.locator('.score-card').count(),0);
  for(const [width,height] of [[1280,720],[390,844],[320,568]]){
    await page.setViewportSize({width,height});
    assert.ok((await button('选择音频').boundingBox()).y<height);
    await page.screenshot({path:`tests/output/flow-home-${width}.png`});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await page.setViewportSize({width:1280,height:720});
  await open(fixture);await ready();
  assert.ok(await page.getByText(/原录音未关联/).isVisible());
  await button('编辑音符').click();
  const sheet=page.getByRole('group',{name:/选音编辑/});
  await sheet.focus();await sheet.press('ArrowRight');await sheet.press('ArrowRight');
  await page.locator('.score-note[data-note-id="e"][data-anchor-onset=true] .score-hitbox').click();
  await page.waitForFunction(()=>document.querySelector('input[aria-label="音高 MIDI"]')?.value==='64');
  await page.getByLabel('音高 MIDI',{exact:true}).fill('65');
  await button('应用修改').click();
  await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.activeVersion==='1');
  await ready();await button('结束校对').click();
  const edited=await fingerprint();
  await page.getByText('乐谱参数',{exact:true}).click();
  await page.getByLabel('速度（BPM）',{exact:true}).fill('135');
  let fail=true;
  await page.route('**/reconfigure',route=>fail?route.fulfill({status:503,json:{error:'temporary error'}}):route.continue());
  await button('应用乐谱参数').click();
  await page.getByRole('alert').filter({hasText:'未能生成新谱'}).waitFor();
  assert.equal(await fingerprint(),edited);
  const old=await save('tests/output/flow-before-rebuild.acproject.json');
  assert.equal(old.versions[1].editedNotes.find(note=>note.id==='e').midi,65);
  fail=false;
  await button('应用乐谱参数').click();
  await page.waitForFunction(()=>document.querySelector('.gf-score')?.dataset.activeVersion==='2');
  await ready();
  const next=await save('tests/output/flow-rebuilt.acproject.json');
  assert.deepEqual(next.versions[1],old.versions[1]);
  assert.equal(next.versions[2].bpm,135);
  assert.equal(next.versions[2].parent,1);
  assert.equal(next.versions[2].editedNotes.find(note=>note.id==='e').midi,65);
  await open('tests/output/flow-rebuilt.acproject.json');
  await page.waitForFunction(()=>!document.querySelector('.project-notice'));
  await ready();
  const reopened=await save('tests/output/flow-reopened.acproject.json');
  assert.deepEqual(reopened.versions,next.versions);
  report.settingsFailureRetryAndRestore=true;
  await button('撤销').click();await ready();
  assert.equal(await fingerprint(),edited);
  await page.getByLabel('查看版本',{exact:true}).selectOption('0');
  await open(fixture);
  await page.getByRole('dialog').waitFor();
  await button('继续编辑').click();
  assert.equal(await score.getAttribute('data-active-version'),'0');
  await open(fixture);await page.getByRole('dialog').waitFor();
  await button('放弃修改').click();await ready();
  report.dirtyGuard=true;
  for(const [width,height] of [[1200,700],[1199,700],[1024,600],[932,430],[390,844],[320,568]]){
    await page.setViewportSize({width,height});
    await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth);
    const svg=await page.locator('.score-page:visible svg').boundingBox();
    assert.ok(svg.width>=Math.min(width-90,280),JSON.stringify({width,height,svg}));
    await page.screenshot({path:`tests/output/flow-score-${width}.png`});
  }
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('tab',{name:'工具',exact:true}).click();
  await button('编辑音符').click();
  await page.locator('.inline-review').waitFor();
  assert.equal(await page.locator('.score-note[tabindex="0"]').count(),0);
  assert.ok(await page.locator('.paged-staff').isVisible());
  report.responsiveEditing=true;
  assert.deepEqual(errors,[]);
  await fs.writeFile('tests/output/flow-checks.json',JSON.stringify(report,null,2));
  console.log(report);
}catch(error){await page.screenshot({path:'tests/output/flow-failure.png'}).catch(()=>{});throw error;}
finally{await browser.close();}
