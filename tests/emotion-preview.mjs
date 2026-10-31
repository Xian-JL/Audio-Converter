import {chromium,browserPath} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const source=JSON.parse(await fs.readFile('exports/情感器乐-呜-对照示例.acproject.json','utf8'));
const original=JSON.parse(source.source.identityNotesJson).map(n=>({id:n.id,start:n.start,end:n.end,pitches:[n.midi],staff:1}));
const takes=Object.values(source.textureSets)[0].items;
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
try{
 const page=await browser.newPage();await page.route('**/api/**',r=>r.fulfill({status:200,json:{ready:true,engine:'game',scoreVersion:20}}));await page.goto('http://127.0.0.1:5173');
 const results=[];
 for(const take of takes){
  const region=take.references.find(r=>r.kind==='interlude'),left=region.start-6,right=region.end+6;
  const name=take.settings.emotion.engine==='emo'?'EMO-呜-间奏钢琴试听.wav':'MIDI-Emotion-呜-间奏钢琴试听.wav';
  const result=await page.evaluate(async({events,left,right})=>{const harness=await import('/tests/emotion-audio.ts');return harness.render(events,left,right);},{events:[...original,...take.events],left,right});
  assert.ok(result.rms>1e-6&&result.peak<1);await fs.writeFile('exports/'+name,Buffer.from(result.wav,'base64'));
  results.push({engine:take.settings.emotion.engine,file:name,peak:result.peak,rms:result.rms,seconds:result.seconds,sourceStart:left,sourceEnd:right});
 }
 await fs.writeFile('tests/output/emotion-audio-checks.json',JSON.stringify({samePiano:true,levels:[60,40],nativeVelocities:true,context:'Saved GF and blocks, six seconds before/after the instrumental section; synthesized, not original audio.',results},null,2));console.log(JSON.stringify(results,null,2));
}finally{await browser.close();}
