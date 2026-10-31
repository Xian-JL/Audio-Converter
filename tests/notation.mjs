import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import ts from 'typescript';
import {chromium,browserPath} from './browser-runtime.mjs';

// Real browser DOMParser/XMLSerializer; no added application dependencies.
const source=await fs.readFile('src/lib/notation.ts','utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText;
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
try {
  const page=await browser.newPage();
  await page.evaluate(async code=>{window.notation=await import(URL.createObjectURL(new Blob([code],{type:'text/javascript'})));},compiled);
  const result=await page.evaluate(()=>{
    const {simplifyNotation}=window.notation;
    const check=(condition,message)=>{if(!condition) throw Error(message);};
    const note=(id,duration,type,ties='',options={})=>{
      const {voice=1,staff=1,chord=false,rest=false,extra='',hidden=false,step='C',octave=4,dots=0}=options;
      return `<note${id?` id="${id}"`:''}${hidden?' print-object="no" print-spacing="yes"':''}>${chord?'<chord/>':''}${rest?'<rest/>':`<pitch><step>${step}</step><octave>${octave}</octave></pitch>`}<duration>${duration}</duration>${[...ties].map(t=>`<tie type="${t==='s'?'start':'stop'}"/>`).join('')}<voice>${voice}</voice><type>${type}</type>${'<dot/>'.repeat(dots)}<staff>${staff}</staff>${ties||extra?`<notations>${[...ties].map(t=>`<tied type="${t==='s'?'start':'stop'}"/>`).join('')}${extra}</notations>`:''}</note>`;
    };
    const rest=(d,type,o={})=>note('',d,type,'',{rest:true,...o});
    function xml(measures,meter='4/4',divisions=32) {
      const [beats,beat]=meter.split('/');
      return `<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">${measures.map((body,i)=>`<measure number="${i+1}">${i===0?`<attributes><divisions>${divisions}</divisions><time><beats>${beats}</beats><beat-type>${beat}</beat-type></time></attributes>`:''}${body}</measure>`).join('')}</part></score-partwise>`;
    }
    // Independent reader: retain attacks, tied sustain, per-voice clocks and non-note anchors.
    function read(text,offsets) {
      const doc=new DOMParser().parseFromString(text,'application/xml'),notes=[],anchors=[],coverage=[];
      [...doc.querySelectorAll('part > measure')].forEach((measure,i)=>{
        let cursor=0,previous=0;
        for(const n of measure.children) {
          if(n.tagName==='backup'||n.tagName==='forward') {
            anchors.push([i,n.tagName,cursor,n.textContent]);cursor+=(n.tagName==='backup'?-1:1)*Number(n.querySelector('duration').textContent);continue;
          }
          if(n.tagName!=='note') {anchors.push([i,n.tagName,cursor,n.outerHTML]);continue;}
          const duration=Number(n.querySelector('duration').textContent),isChord=!!n.querySelector('chord');
          const start=(isChord?previous:cursor)+offsets[i],end=start+duration;
          if(!isChord) {previous=cursor;cursor+=duration;}
          const staff=n.querySelector('staff')?.textContent||'1',voice=n.querySelector('voice')?.textContent||'1',isRest=!!n.querySelector('rest');
          const id=(n.getAttribute('id')||'').replace(/-t\d+(?:-p\d+)?$/,'');
          const p=isRest?'rest':n.querySelector('pitch').outerHTML,visible=n.getAttribute('print-object')!=='no';
          const stop=!!n.querySelector('tie[type="stop"]'),tie=!!n.querySelector('tie[type="start"]');
          const written=[...n.querySelectorAll('notations > tied')].map(t=>t.getAttribute('type')).sort();
          const sound=[...n.querySelectorAll(':scope > tie')].map(t=>t.getAttribute('type')).sort();
          check(JSON.stringify(written)===JSON.stringify(sound),'sound/written ties differ');
          notes.push({start,end,staff,voice,id,p,visible,stop,tie});
          coverage.push([i,staff,voice,start,end,isChord]);
        }
      });
      const lanes=new Map();
      for(const n of notes) {
        const key=JSON.stringify([n.staff,n.voice,n.p,n.id,n.visible]),lane=lanes.get(key)||[],last=lane.at(-1);
        if(last&&last.end===n.start&&(n.p==='rest'||last.tie&&n.stop)) {last.end=n.end;last.tie=n.tie;}
        else lane.push({...n});
        lanes.set(key,lane);
      }
      return {signature:JSON.stringify([...lanes].sort(([a],[b])=>a.localeCompare(b))),anchors:JSON.stringify(anchors),notes,doc,coverage};
    }
    const checks=[];
    function run(name,source,{meter='4/4',divisions=32,lengths=[128],pickup=false,expectedRemoved,expectedTypes}={}) {
      let offset=0;const measures=lengths.map((length,i)=>{const m={number:i+1,startTick:offset,endTick:offset+length,pickup:pickup&&i===0};offset+=length;return m;});
      const before=read(source,measures.map(m=>m.startTick)),logical=new Map(),fragments=[];
      for(const n of before.notes) if(n.staff==='1'&&n.voice==='1'&&n.p!=='rest') {
        const old=logical.get(n.id);
        logical.set(n.id,{id:n.id,midi:60,startTick:old?.startTick??n.start,endTick:n.end});
        fragments.push({noteId:n.id,startTick:n.start,endTick:n.end,midi:60});
      }
      const score={divisions,meter,measures,notes:[...logical.values()],noteCount:logical.size,fragments,events:[{start:0,end:1,pitches:[60],staff:1}]};
      const frozen=JSON.stringify(score),result=simplifyNotation(source,score),after=read(result.xml,measures.map(m=>m.startTick));
      check(result.status!=='preserved',name+': fell back');
      check(frozen===JSON.stringify(score),name+': mutated score/events');
      check(before.signature===after.signature,name+': changed attacks, durations, visibility or ties');
      check(before.anchors===after.anchors,name+': moved backup, forward or markings');
      check(result.removedFragments>=0,name+': added note elements');
      if(expectedRemoved!==undefined) check(result.removedFragments===expectedRemoved,name+': removed '+result.removedFragments);
      if(expectedTypes) check(JSON.stringify([...after.doc.querySelectorAll('note > type')].map(n=>n.textContent))===JSON.stringify(expectedTypes),name+': types');
      // Exact note type/dot arithmetic independently checked for every output symbol.
      const typeValues={whole:128,half:64,quarter:32,eighth:16,'16th':8,'32nd':4,'64th':2,'128th':1,'256th':.5};
      for(const n of after.doc.querySelectorAll('note')) {
        const type=n.querySelector('type')?.textContent,dots=n.querySelectorAll(':scope > dot').length;
        if(type) check(typeValues[type]*divisions/32*(2-1/2**dots)===Number(n.querySelector('duration').textContent),name+': inexact glyph');
        else check(n.querySelector('rest[measure="yes"]'),name+': missing note type');
      }
      const again=simplifyNotation(result.xml,score);
      check(again.xml===result.xml,name+': not idempotent');
      check(JSON.stringify(again.fragments)===JSON.stringify(result.fragments),name+': fragment map not idempotent');
      check(new Set(result.fragments.map(f=>f.noteId)).size===logical.size,name+': lost logical melody');
      checks.push({name,removed:result.removedFragments});return {result,after,score};
    }
    const sustained=Array.from({length:4},(_,i)=>note(`gf-1-t${i*32}`,32,'quarter',i===0?'s':i===3?'e':'es')).join('');
    run('four tied quarters become a whole',xml([sustained]),{expectedRemoved:3,expectedTypes:['whole']});
    run('repeated real attacks remain',xml([Array.from({length:4},(_,i)=>note(`gf-${i}-t${i*32}`,32,'quarter')).join('')]),{expectedRemoved:0});
    run('slur is not a tie',xml([Array.from({length:4},(_,i)=>note(`gf-${i}-t${i*32}`,32,'quarter','',{extra:`<slur type="${i===3?'stop':'start'}"/>`})).join('')]),{expectedRemoved:0});
    run('separate logical identities never merge',xml([note('gf-1-t0',64,'half','s')+note('gf-2-t64',64,'half','e')]),{expectedRemoved:0});
    run('cross-bar ties retained',xml([note('gf-1-t0',64,'half','s')+note('gf-1-t64',64,'half','es'),note('gf-1-t128',64,'half','es')+note('gf-1-t192',64,'half','e')]),{lengths:[128,128],expectedRemoved:2,expectedTypes:['whole','whole']});
    run('double dot exact reduction',xml([note('gf-1-t0',24,'eighth','s',{dots:1})+note('gf-1-t24',4,'32nd','e')+rest(96,'half',{dots:1})+rest(4,'32nd')]),{expectedRemoved:1});
    run('17 ticks never rounded',xml([note('gf-1-t0',16,'eighth','s')+note('gf-1-t16',1,'128th','e')+rest(96,'half',{dots:1})+rest(12,'16th',{dots:1})+rest(3,'64th',{dots:1})]),{expectedRemoved:0});
    const repartitioned=run('new fragment boundaries retain logical identity',xml([note('gf-1-t0',96,'half','s',{dots:1})+note('gf-1-t96',24,'eighth','es',{dots:1})+note('gf-1-t120',6,'32nd','es',{dots:1})+note('gf-1-t126',1,'128th','e')+rest(1,'128th')]),{expectedRemoved:1});
    check(repartitioned.result.fragments.some(f=>f.startTick===112&&f.noteId==='gf-1'),'new fragment start must map to original GF note');
    run('strong midpoint and syncopation preserved',xml([rest(32,'quarter')+note('gf-1-t32',32,'quarter','s')+note('gf-1-t64',32,'quarter','e')+rest(32,'quarter')]),{expectedRemoved:0});
    run('whole measure rest in three-four',xml([rest(32,'quarter')+rest(32,'quarter')+rest(32,'quarter')],'3/4'),{meter:'3/4',lengths:[96],expectedRemoved:2});
    run('hidden whole rest stays hidden',xml([rest(64,'half',{hidden:true})+rest(64,'half',{hidden:true})]),{expectedRemoved:1});
    run('visible and hidden rests do not combine',xml([rest(64,'half')+rest(64,'half',{hidden:true})]),{expectedRemoved:0});
    run('pickup keeps metrical offset',xml([note('gf-1-t0',32,'quarter','s')+note('gf-1-t32',16,'eighth','es')+note('gf-1-t48',8,'16th','e')+rest(8,'16th')]),{lengths:[64],pickup:true,expectedRemoved:2});
    run('compound beat grouping',xml([note('gf-1-t0',24,'eighth','s',{dots:1})+note('gf-1-t24',4,'32nd','es')+note('gf-1-t28',16,'eighth','es')+note('gf-1-t44',4,'32nd','e')+rest(48,'quarter',{dots:1})],'6/8'),{meter:'6/8',lengths:[96],expectedRemoved:3});
    // Valid duration types for dense divisions=64; two fragments become double-dotted eighth.
    run('dense resolution',xml([note('gf-1-t0',48,'eighth','s',{dots:1})+note('gf-1-t48',8,'32nd','e')+rest(128,'half')+rest(64,'quarter')+rest(8,'32nd')],'4/4',64),{divisions:64,lengths:[256],expectedRemoved:1});
    run('articulation protects tied chain',xml([note('gf-1-t0',64,'half','s',{extra:'<articulations><staccato/></articulations>'})+note('gf-1-t64',64,'half','e')]),{expectedRemoved:0});
    run('direction remains at its time',xml([note('gf-1-t0',64,'half','s')+'<direction><direction-type><dynamics><p/></dynamics></direction-type></direction>'+note('gf-1-t64',64,'half','e')]),{expectedRemoved:0});
    const chord=(at,duration,type,ties,upper='E')=>note(`amt-1-t${at}-p60`,duration,type,ties,{voice:2,staff:2})+note(`amt-1-t${at}-p64`,duration,type,ties,{voice:2,staff:2,chord:true,step:upper});
    run('complete chord tie simplifies without double clock',xml([rest(128,'whole')+'<backup><duration>128</duration></backup>'+chord(0,64,'half','s')+chord(64,64,'half','e')]),{expectedRemoved:2});
    run('duplicate simultaneous pitches stay distinct',xml([rest(128,'whole')+'<backup><duration>128</duration></backup>'+chord(0,64,'half','s','C')+chord(64,64,'half','e','C')]),{expectedRemoved:0});
    run('partial chord sustain does not merge changed upper tone',xml([rest(128,'whole')+'<backup><duration>128</duration></backup>'+note('amt-1-t0-p60',64,'half','s',{voice:2,staff:2})+note('amt-upper-t0-p64',64,'half','',{voice:2,staff:2,chord:true,step:'E'})+note('amt-1-t64-p60',64,'half','e',{voice:2,staff:2})+note('amt-next-t64-p65',64,'half','',{voice:2,staff:2,chord:true,step:'F'})]),{expectedRemoved:0});
    run('independent sustained lane simplifies under changing lane',xml([rest(128,'whole')+'<backup><duration>128</duration></backup>'+chord(0,64,'half','s')+chord(64,64,'half','e')+'<backup><duration>128</duration></backup>'+note('upper-1-t0',64,'half','',{voice:3,staff:2,step:'G'})+note('upper-2-t64',64,'half','',{voice:3,staff:2,step:'A'})]),{expectedRemoved:2});
    run('forward leaves an exact gap',xml([note('gf-1-t0',16,'eighth')+'<forward><duration>16</duration></forward>'+note('gf-2-t32',32,'quarter','s')+note('gf-2-t64',32,'quarter','e')+rest(32,'quarter')]),{expectedRemoved:0});
    const protectedAttrs=xml([sustained]).replace('<notations>','<notations print-object="no">');
    run('notation attributes protected',protectedAttrs,{expectedRemoved:1}); // remaining unmarked suffix can still simplify
    const invalid=simplifyNotation('<invalid/>',{divisions:32,meter:'4/4',measures:[],notes:[],noteCount:0,fragments:[]});
    check(invalid.status==='preserved'&&invalid.xml==='<invalid/>','unsupported XML must keep original');
    return checks;
  });
  assert.ok(result.length>=20);console.log(JSON.stringify(result,null,2));
  console.log('MusicXML equivalence, exact glyphs, identity, marks, clocks and idempotence passed.');
} finally {await browser.close();}
