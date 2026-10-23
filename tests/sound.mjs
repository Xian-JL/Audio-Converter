import {chromium,browserPath} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
try{
 const page=await browser.newPage();await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.goto('http://127.0.0.1:5173',{waitUntil:'domcontentloaded',timeout:120000});
 const result=await page.evaluate(async()=>{const harness=await import('/tests/sound-harness.ts');return {long:await harness.longNotes(),stress:await harness.stress()};});
 for(const sound of result.long){assert.ok(sound.atOneSecond>.00001);assert.ok(sound.atFiveSeconds>.00001);assert.ok(sound.afterRelease<sound.atFiveSeconds*.1);assert.ok(sound.peak<1);assert.ok(Math.abs(sound.normalizationDb)<=6);}
 assert.ok(result.stress.ticks>20);assert.ok(result.stress.at>=0&&result.stress.at<1.2);assert.equal(result.stress.paused,result.stress.stopped);
 await fs.writeFile('tests/output/sound-checks.json',JSON.stringify(result,null,2));console.log('Eight sustained sample instruments, release, normalization and background/stall loop checks passed');
}finally{await browser.close();}
