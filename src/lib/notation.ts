import type { ScoreData } from './api';

/** A derived engraving only. Never write this XML or its fragments into ScoreData. */
export const NOTATION_VERSION = 'equivalent-v1';
type Shape = { ticks:number; type:string; dots:number };
type Context = { divisions:number; meter:string; length:number; pickup?:boolean };
type Group = { nodes:Element[]; start:number; end:number; voice:string; staff:string };
type Bar = { element:Element; groups:Group[]; context:Context; offset:number };
type Fragment = NonNullable<ScoreData['fragments']>[number];
export type Notation = { xml:string; fragments:Fragment[]; version:string; removedFragments:number; status:'simplified'|'unchanged'|'preserved' };

const children = (node:Element, name:string) => [...node.children].filter(n=>n.tagName===name);
const child = (node:Element, name:string) => children(node,name)[0];
const value = (node:Element, name:string, fallback='') => child(node,name)?.textContent||fallback;
const identity = (node:Element) => (node.getAttribute('id')||'').replace(/-t\d+(?:-p\d+)?$/,'');
const pitch = (node:Element) => child(node,'pitch')?.outerHTML||child(node,'rest')?.outerHTML||'';
const hasTie = (node:Element, type:string) => children(node,'tie').some(n=>n.getAttribute('type')===type);
const attributes = (node:Element) => [...node.attributes].filter(a=>a.name!=='id').map(a=>[a.name,a.value]).sort();
const groupKey = (group:Group) => JSON.stringify(group.nodes.map(n=>[identity(n),pitch(n),attributes(n),value(n,'voice','1'),value(n,'staff','1'),value(n,'stem')]));

function shapes(divisions:number):Shape[] {
  const types=['whole','half','quarter','eighth','16th','32nd','64th','128th','256th'];
  return types.flatMap((type,i)=>[0,1,2].map(dots=>({ticks:divisions*4/2**i*(2-1/2**dots),type,dots})))
    .filter(s=>Number.isSafeInteger(s.ticks)&&s.ticks>0).sort((a,b)=>b.ticks-a.ticks||a.dots-b.dots);
}

function readable(start:number, shape:Shape, context:Context, rest:boolean) {
  const [beats,denominator]=context.meter.split('/').map(Number),unit=context.divisions*4/denominator;
  const full=beats*unit,offset=context.pickup?full-context.length:0;
  const at=start+offset,end=at+shape.ticks;
  if (rest&&shape.dots===2) return false;
  if (denominator===8&&beats%3===0) {
    const beat=unit*3,local=at%beat;
    // Compound beats stay visible; a full-bar sustained note is unambiguous.
    if (!rest&&at===0&&shape.ticks===full) return true;
    if (local===0) return shape.ticks<=beat;
    return shape.ticks<=unit&&end<=at-local+beat&&end<=at-at%unit+unit;
  }
  if (!['2/4','3/4','4/4'].includes(context.meter)) {
    // No inferred 2+3/3+2 grouping for asymmetric meters.
    return shape.ticks<=unit&&Math.floor(at/unit)===Math.floor((end-1)/unit);
  }
  if (rest) {
    if (shape.dots) return false;
    if (shape.ticks>unit) return context.meter==='4/4'&&shape.ticks===2*unit&&at%(2*unit)===0;
    if (Math.floor(at/unit)!==Math.floor((end-1)/unit)) return false;
  }
  // A new symbol may not hide a boundary stronger than its starting position.
  // Tick resolutions are powers of two. Zero is the strongest position.
  const strength=at===0?full:at&-at;
  return end<=at+strength;
}

/** Exact, bounded dynamic programming; no snapping, tolerances or cross-bar values. */
export function notationPlan(start:number, end:number, context:Context, rest=false):Shape[]|null {
  if (!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||end<=start||end>context.length||context.length>4096) return null;
  const options=shapes(context.divisions),cost=new Array<number>(end-start+1).fill(Infinity);
  const next=new Map<number,Shape>();cost[end-start]=0;
  for(let at=end-1;at>=start;at--) for(const shape of options) {
    if(at+shape.ticks>end||!readable(at,shape,context,rest)) continue;
    const candidate=8192+shape.dots+cost[at+shape.ticks-start];
    if(candidate<cost[at-start]) {cost[at-start]=candidate;next.set(at,shape);}
  }
  if(!Number.isFinite(cost[0])) return null;
  const result:Shape[]=[];
  for(let at=start;at<end;) {const shape=next.get(at)!;result.push(shape);at+=shape.ticks;}
  return result;
}

function eligible(group:Group) {
  // Duplicate simultaneous pitches do not identify a unique tied lane. Preserve them.
  if(new Set(group.nodes.map(pitch)).size!==group.nodes.length) return false;
  const allowed=new Set(['chord','pitch','rest','duration','tie','voice','type','dot','stem','staff','notations']);
  return group.nodes.every(n=>{
    if([...n.attributes].some(a=>!['id','print-object','print-spacing'].includes(a.name))) return false;
    if([...n.children].some(c=>!allowed.has(c.tagName))) return false;
    if([...n.children].some(c=>!['pitch','rest','tie','notations'].includes(c.tagName)&&c.attributes.length)) return false;
    if(Number(value(n,'duration'))!==group.end-group.start||children(n,'dot').length>2) return false;
    if(child(n,'rest')?.children.length) return false;
    if(child(n,'rest')&&child(n,'pitch')) return false;
    if(!child(n,'rest')&&!child(n,'pitch')) return false;
    const ties=children(n,'tie'),notations=children(n,'notations');
    if(notations.length>1||notations.some(nt=>nt.attributes.length||[...nt.children].some(t=>t.tagName!=='tied'))) return false;
    const written=notations.flatMap(nt=>children(nt,'tied'));
    const valid=(t:Element)=>t.attributes.length===1&&['start','stop'].includes(t.getAttribute('type')||'');
    if(![...ties,...written].every(valid)) return false;
    const types=(ts:Element[])=>ts.map(t=>t.getAttribute('type')).sort().join(',');
    if(types(ties)!==types(written)||new Set(ties.map(t=>t.getAttribute('type'))).size!==ties.length) return false;
    return !child(n,'rest')||!ties.length;
  });
}

function parseBars(doc:Document, score:ScoreData):Bar[] {
  const parts=children(doc.documentElement,'part');
  if(doc.documentElement.tagName!=='score-partwise'||parts.length!==1) throw Error('Unsupported notation part');
  const measures=children(parts[0],'measure');
  if(measures.length!==score.measures.length) throw Error('Notation measure count changed');
  let divisions=score.divisions||32,meter=score.meter;
  return measures.map((element,i)=>{
    const meta=score.measures[i],offset=meta.startTick;
    if(offset===undefined||meta.endTick===undefined) throw Error('Notation grid is missing');
    let cursor=0,previous:Group|undefined;const groups:Group[]=[];
    for(const n of element.children) {
      if(n.tagName==='attributes') {
        divisions=Number(value(n,'divisions',String(divisions)));
        const time=child(n,'time');if(time) meter=`${value(time,'beats')}/${value(time,'beat-type')}`;
      }
      if(n.tagName==='backup'||n.tagName==='forward') cursor+=(n.tagName==='backup'?-1:1)*Number(value(n,'duration'));
      if(n.tagName!=='note') {previous=undefined;continue;}
      const duration=Number(value(n,'duration')),voice=value(n,'voice','1'),staff=value(n,'staff','1');
      if(!Number.isSafeInteger(duration)||duration<=0||child(n,'grace')) throw Error('Unsupported note duration');
      if(child(n,'chord')) {
        if(!previous||previous.voice!==voice||previous.staff!==staff) throw Error('Unsupported chord');
        previous.nodes.push(n);
      } else {
        previous={nodes:[n],start:cursor,end:cursor+duration,voice,staff};groups.push(previous);cursor+=duration;
      }
    }
    if(divisions!==score.divisions||meter!==score.meter||groups.some(g=>g.start<0||g.end>meta.endTick!-offset)) throw Error('Unsupported notation grid');
    return {element,groups,offset,context:{divisions,meter,length:meta.endTick-offset,pickup:!!meta.pickup}};
  });
}

function connected(a:Group,b:Group) {
  if(a.end!==b.start||a.voice!==b.voice||a.staff!==b.staff||groupKey(a)!==groupKey(b)) return false;
  if(a.nodes.at(-1)!.nextElementSibling!==b.nodes[0]) return false;
  return a.nodes.every((n,i)=>child(n,'rest')?!!child(b.nodes[i],'rest'):hasTie(n,'start')&&hasTie(b.nodes[i],'stop'));
}

function setText(node:Element,name:string,text:string,after?:Element) {
  const existing=child(node,name);
  if(existing) {existing.textContent=text;return existing;}
  const created=node.ownerDocument.createElement(name);created.textContent=text;
  node.insertBefore(created,after?after.nextSibling:null);return created;
}

function rewrite(run:Group[],plan:Shape[],bar:Bar,wholeRest:boolean) {
  const first=run[0],last=run.at(-1)!,replacement:Element[]=[];let at=first.start;
  for(const shape of plan) {
    first.nodes.forEach((template,i)=>{
      const n=template.cloneNode(true) as Element;
      children(n,'tie').forEach(t=>t.remove());children(n,'notations').forEach(t=>t.remove());children(n,'dot').forEach(t=>t.remove());
      const duration=setText(n,'duration',String(shape.ticks));
      const type=setText(n,'type',shape.type,child(n,'voice')||duration);
      for(let j=0;j<shape.dots;j++) n.insertBefore(n.ownerDocument.createElement('dot'),type.nextSibling);
      if(wholeRest) {child(n,'rest')!.setAttribute('measure','yes');type.remove();children(n,'dot').forEach(t=>t.remove());}
      if(n.hasAttribute('id')) {
        const original=template.getAttribute('id')!;
        // Only the server's derived fragment suffix changes. Logical identity stays intact.
        n.setAttribute('id',original.replace(/-t\d+(-p\d+)?$/,`-t${bar.offset+at}$1`));
      }
      if(!child(n,'rest')) {
        const stop=at>first.start||hasTie(template,'stop');
        const start=at+shape.ticks<last.end||hasTie(last.nodes[i],'start');
        const nt=n.ownerDocument.createElement('notations');
        for(const [active,kind] of [[stop,'stop'],[start,'start']] as const) if(active) {
          const tie=n.ownerDocument.createElement('tie');tie.setAttribute('type',kind);n.insertBefore(tie,child(n,'voice')||type);
          const tied=n.ownerDocument.createElement('tied');tied.setAttribute('type',kind);nt.appendChild(tied);
        }
        if(nt.children.length) n.appendChild(nt);
      }
      replacement.push(n);
    });
    at+=shape.ticks;
  }
  const parent=first.nodes[0].parentNode!;
  for(const n of replacement) parent.insertBefore(n,first.nodes[0]);
  for(const g of run) for(const n of g.nodes) n.remove();
}

/** Per-pitch timing and tie-boundary identity, including chords that only partly sustain. */
function semantics(bars:Bar[]) {
  return bars.map(bar=>{
    const lanes=new Map<string,{start:number;end:number;stop:boolean;tie:boolean}[]>();
    for(const g of bar.groups) for(const n of g.nodes) {
      // measure="yes" changes only the rest glyph, not its duration.
      const p=child(n,'rest')?'rest':pitch(n);
      const key=JSON.stringify([g.staff,g.voice,p,identity(n),attributes(n),value(n,'stem')]);
      const lane=lanes.get(key)||[],previous=lane.at(-1),stop=hasTie(n,'stop'),tie=hasTie(n,'start');
      if(previous&&previous.end===g.start&&(p==='rest'||previous.tie&&stop)) {previous.end=g.end;previous.tie=tie;}
      else lane.push({start:g.start,end:g.end,stop,tie});
      lanes.set(key,lane);
    }
    return [...lanes].sort(([a],[b])=>a.localeCompare(b));
  });
}

function melodyFragments(bars:Bar[], score:ScoreData):Fragment[] {
  const notes=score.notes||[],result:Fragment[]=[];const byId=new Map(notes.map(n=>[n.id,n]));
  for(const bar of bars) for(const g of bar.groups) if(g.staff==='1'&&g.voice==='1') for(const n of g.nodes) {
    if(child(n,'rest')) continue;
    const logical=byId.get(identity(n)),startTick=bar.offset+g.start,endTick=bar.offset+g.end;
    if(!logical||startTick<logical.startTick||endTick>logical.endTick) throw Error('Notation lost a melody identity');
    result.push({noteId:logical.id,startTick,endTick,midi:logical.midi});
  }
  if(new Set(result.map(f=>f.noteId)).size!==score.noteCount) throw Error('Notation lost a melody onset');
  return result;
}

/** Always derives from source XML. Unsupported structures keep their original engraving. */
export function simplifyNotation(xml:string, score:ScoreData):Notation {
  const original:Notation={xml,fragments:score.fragments||[],version:NOTATION_VERSION,removedFragments:0,status:'unchanged'};
  try {
    const doc=new DOMParser().parseFromString(xml,'application/xml');
    if(doc.querySelector('parsererror')) throw Error('Invalid notation XML');
    const bars=parseBars(doc,score),before=JSON.stringify(semantics(bars));
    const count=bars.reduce((n,b)=>n+b.groups.reduce((s,g)=>s+g.nodes.length,0),0);
    let changed=false;
    for(const bar of bars) {
      for(let i=0;i<bar.groups.length;) {
        const first=bar.groups[i],run=[first];let j=i+1;
        if(!eligible(first)) {i=j;continue;}
        while(j<bar.groups.length&&eligible(bar.groups[j])&&connected(run.at(-1)!,bar.groups[j])) run.push(bar.groups[j++]);
        const last=run.at(-1)!,rest=!!child(first.nodes[0],'rest');
        const [beats,denominator]=bar.context.meter.split('/').map(Number);
        const wholeRest=rest&&first.nodes.length===1&&first.start===0&&last.end===bar.context.length&&!bar.context.pickup&&bar.context.length===beats*bar.context.divisions*4/denominator;
        const plan=wholeRest?[{ticks:bar.context.length,type:'whole',dots:0}]:run.length>1?notationPlan(first.start,last.end,bar.context,rest):null;
        if(plan&&(plan.length<run.length||wholeRest&&child(first.nodes[0],'rest')?.getAttribute('measure')!=='yes')) {
          rewrite(run,plan,bar,wholeRest);changed=true;
        }
        i=j;
      }
    }
    if(!changed) return {...original,fragments:melodyFragments(bars,score)};
    const derived=parseBars(doc,score);
    if(JSON.stringify(semantics(derived))!==before) throw Error('Notation timing or ties changed');
    const fragments=melodyFragments(derived,score);
    const remaining=derived.reduce((n,b)=>n+b.groups.reduce((s,g)=>s+g.nodes.length,0),0);
    return {xml:new XMLSerializer().serializeToString(doc),fragments,version:NOTATION_VERSION,removedFragments:count-remaining,status:'simplified'};
  } catch(cause) {
    console.warn('Preserving source engraving:',cause);
    return {...original,status:'preserved'};
  }
}
