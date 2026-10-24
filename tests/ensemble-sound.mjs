import {chromium,browserPath} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
await fs.mkdir('tests/output',{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
try{
 const page=await browser.newPage();await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.goto('http://127.0.0.1:5173',{waitUntil:'domcontentloaded',timeout:120000});
 const result=await page.evaluate(async()=>{const harness=await import('/tests/sound-harness.ts');return harness.ensembleSounds();});
 assert.equal(result.results.length,48);for(const sound of result.results){assert.ok(sound.rms>1e-6,JSON.stringify(sound));assert.ok(sound.peak<1);}
 for(const instrument of new Set(result.results.map(r=>r.instrument))){const sounds=result.results.filter(r=>r.instrument===instrument);assert.equal(new Set(sounds.map(s=>s.fingerprint.toFixed(7))).size,4,instrument+' timbres identical');}
 assert.deepEqual(result.mixed.counts,[4,2]);assert.ok(result.mixed.rms>0&&result.mixed.peak<1);assert.ok(result.mixed.stereo>1);assert.equal(new Set(result.mixed.spread.map(p=>p.cents)).size,4);assert.notEqual(result.mixed.fingerprint,result.solo.fingerprint);assert.equal(result.rejected,3);
 await fs.writeFile('tests/output/ensemble-sound.json',JSON.stringify(result,null,2));console.log('All 48 timbres audible/distinct; 4 violins + piano/cello produce six independent, normalized voices');
}finally{await browser.close();}
