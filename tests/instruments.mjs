import {chromium,browserPath} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
await fs.mkdir('tests/output',{recursive:true});
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
try{
 const page=await browser.newPage();await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.goto('http://127.0.0.1:8765');
 const chunk=(await fs.readdir('dist/assets')).find(n=>n.startsWith('esm-')&&n.endsWith('.js'));
 const stats=await page.evaluate(async chunk=>{
  const Tone=await import('/assets/'+chunk),manifest=await(await fetch('/instruments/manifest.json')).json(),results=[];
  const banks=[{id:'piano',samples:{C3:'C3.mp3',C4:'C4.mp3',C5:'C5.mp3'}},...Object.entries(manifest.instruments).map(([id,bank])=>({id,samples:bank.samples}))];
  for(const {id,samples} of banks){
   const buffers={};for(const [note,name] of Object.entries(samples)){const holder=new Tone.ToneAudioBuffer();await holder.load(id==='piano'?'/piano/'+name:`/instruments/${id}/${name}`);buffers[note]=holder.get();holder.dispose();}
   const result=await Tone.Offline(()=>{const sampler=new Tone.Sampler({urls:buffers,attack:.005,release:.15,volume:-12}).toDestination();sampler.triggerAttackRelease(['C4','E4','G4'],.65,.1,.6);},1.2,1,16000);
   const data=result.getChannelData(0);let peak=0,energy=0,fingerprint=0;for(let i=0;i<data.length;i++){peak=Math.max(peak,Math.abs(data[i]));energy+=data[i]*data[i];fingerprint+=data[i]*(i%97);}results.push({id,peak,rms:Math.sqrt(energy/data.length),fingerprint});result.dispose();
  }return results;
 },chunk);
 assert.ok(stats.length>=11);for(const entry of stats){assert.ok(entry.rms>1e-5,entry.id+' is silent');assert.ok(entry.peak<1,entry.id+' clips');}assert.equal(new Set(stats.map(x=>x.fingerprint.toFixed(7))).size,stats.length);
 await fs.writeFile('tests/output/instruments.json',JSON.stringify({count:stats.length,checks:'All instruments decoded from local samples and produced distinct audible offline chords without clipping',stats},null,2));console.log('12 sampled instruments decoded and rendered distinct audible chords');
}finally{await browser.close();}
