import { useEffect, useRef, useState } from 'react';
import { api } from './lib/api';
import type { AccompanimentData, BasicHarmony, ScoreData } from './lib/api';
const words={
  en:{title:'Left-hand arrangement',style:'Texture preference',lyrical:'Lyrical',flowing:'Flowing',syncopated:'Gentle syncopation',density:'Density',levels:['Sparse','Medium','Rich'],variant:'Alternative',generate:'Generate accompaniment',working:'Arranging…',cancel:'Cancel',version:'Playback version',block:'Block-chord reference',take:'Arrangement',export:'Export arrangement',error:'Unable to arrange. Please retry.',missing:'Accompaniment resources are missing. Run SetupTexture.cmd and restart.',meter:'Expressive accompaniment currently supports 4/4. The block-chord reference is still available.'},
  zh:{title:'左手编配',style:'织体倾向',lyrical:'抒情',flowing:'流动',syncopated:'轻切分',density:'密度',levels:['疏','中','密'],variant:'备选方案',generate:'生成丰富伴奏',working:'正在编配…',cancel:'取消编配',version:'试听版本',block:'柱式对照',take:'伴奏',export:'导出编配',error:'无法完成编配，请重试。',missing:'伴奏资源未就绪，请运行 SetupTexture.cmd 后重启。',meter:'丰富伴奏目前支持 4/4，仍可使用柱式对照。'},
};
export default function Accompaniment({score,harmony,jobId,language,items,active,onGenerated,onSelect,onBeforeChange,onBusyChange,busy}:{score:ScoreData;harmony:BasicHarmony;jobId:string;language:'en'|'zh';items:AccompanimentData[];active:number;onGenerated:(data:AccompanimentData)=>void;onSelect:(index:number)=>void;onBeforeChange:()=>void;onBusyChange:(busy:boolean)=>void;busy:boolean}){
  const text=words[language];const [style,setStyle]=useState<'lyrical'|'flowing'|'syncopated'>('lyrical'),[density,setDensity]=useState(1),[variant,setVariant]=useState(0),[voicing,setVoicing]=useState<'layered'|'compact'>('layered'),[working,setWorking]=useState(false),[error,setError]=useState('');
  const token=useRef<string|null>(null);
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>{request.current?.abort();if(token.current)void fetch(`/api/jobs/${jobId}/texture/${token.current}`,{method:'DELETE',keepalive:true}).catch(()=>{});onBusyChange(false);},[]);
  const cancel=()=>{if(token.current)void api(`/api/jobs/${jobId}/texture/${token.current}`,{method:'DELETE'}).catch(()=>{});token.current=null;request.current?.abort();setWorking(false);onBusyChange(false);};
  const generate=async()=>{
    const controller=new AbortController();token.current=crypto.randomUUID().replaceAll('-','');request.current?.abort();request.current=controller;onBeforeChange();setWorking(true);onBusyChange(true);setError('');
    try{
      const result=await api<AccompanimentData>(`/api/jobs/${jobId}/texture`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bpm:score.bpm,meter:score.meter,key:score.key,editedNotes:score.editedNotes,identityNotesJson:score.identityNotesJson,anchorNoteId:score.downbeat?.noteId,sourceFingerprint:score.scoreFingerprint,harmonyFingerprint:harmony.fingerprint,locks:harmony.locks,phraseStarts:harmony.phraseStarts,chordOffsetMs:harmony.alignment.offsetMs,style,density,variant,voicing,requestId:token.current})});
      if(!controller.signal.aborted){if(result.harmonyFingerprint!==harmony.fingerprint||result.sourceFingerprint!==score.scoreFingerprint)throw Error('Score changed');onGenerated(result);}
    }catch(cause){if(!controller.signal.aborted){const message=cause instanceof Error?cause.message:'';setError(message.includes('resources')?text.missing:message.includes('4/4')?text.meter:text.error);}}
    finally{if(!controller.signal.aborted){token.current=null;setWorking(false);onBusyChange(false);}}
  };
  const download=()=>{
    const selected=items[active];if(!selected)return;
    const value={schemaVersion:1,kind:'left-hand-arrangement',sourceName:score.sourceName,sourceSha256:score.sourceSha256,bpm:score.bpm,meter:score.meter,key:score.key,downbeat:score.downbeat,grid:score.grid,harmony,accompaniment:selected};
    const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='piano-accompaniment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <section className="accompaniment-panel" aria-label={text.title}><h3>{text.title}</h3>
    <div className="accompaniment-options"><label>{text.style}<select aria-label={text.style} value={style} disabled={working||busy} onChange={e=>setStyle(e.target.value as typeof style)}>{(['lyrical','flowing','syncopated'] as const).map(s=><option key={s} value={s}>{text[s]}</option>)}</select></label>
    <label>{text.density}<select aria-label={text.density} value={density} disabled={working||busy} onChange={e=>setDensity(Number(e.target.value))}>{text.levels.map((name,i)=><option key={i} value={i}>{name}</option>)}</select></label>
    <label>{text.variant}<select aria-label={text.variant} value={variant} disabled={working||busy} onChange={e=>setVariant(Number(e.target.value))}>{[0,1,2].map(i=><option key={i} value={i}>{i+1}</option>)}</select></label></div>
    <label className="voice-toggle"><input type="checkbox" checked={voicing==='layered'} disabled={working||busy} onChange={e=>setVoicing(e.target.checked?'layered':'compact')}/>{language==='zh'?'保留左手独立声部与音长':'Independent left-hand voices and durations'}</label>
    <div className="gf-review-row"><button className="primary-button" disabled={working||busy} onClick={()=>void generate()}>{working?text.working:text.generate}</button>{working&&<button onClick={cancel}>{text.cancel}</button>}
    <label>{text.version}<select aria-label={text.version} value={active} disabled={working||busy} onChange={e=>onSelect(Number(e.target.value))}><option value={-1}>{text.block}</option>{items.map((item,i)=><option key={item.fingerprint} value={i}>{text.take} {i+1} · {text[item.settings.style]} · {text.levels[item.settings.density]} · {item.settings.voicing==='layered'?(language==='zh'?'独立声部':'Layered'):(language==='zh'?'紧凑':'Compact')}</option>)}</select></label>{active>=0&&<button disabled={working||busy} onClick={download}>{text.export}</button>}</div>
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
  </section>;
}
