import { useEffect, useRef, useState } from 'react';
import { api, clock } from './lib/api';
import type { BasicHarmony as Harmony, ScoreData } from './lib/api';

const words={
  en:{title:'Melody-led block chords',generate:'Generate block chords',regenerate:'Recalculate unlocked chords',working:'Preparing chords…',measure:'Measure / time',chord:'Chord',tones:'Chord tones',lock:'Lock',phrase:'New phrase',hear:'Hear measure',export:'Export chords',review:'Review',saved:'Chord settings saved.',unsaved:'Unable to save chord settings. Export before closing.',error:'Unable to generate chords. Please retry.',suggested:'Suggested',all:'All chords',clear:'Clear locks',offset:'Chord offset (ms; negative = earlier)',apply:'Apply timing'},
  zh:{title:'旋律柱式和弦',generate:'生成柱式和弦',regenerate:'重新推导未锁定和弦',working:'正在配置和弦…',measure:'小节 / 时间',chord:'和弦',tones:'组成音',lock:'锁定',phrase:'新乐句',hear:'试听小节',export:'导出和弦',review:'待核对',saved:'和弦设置已保存。',unsaved:'无法保存和弦设置，请在关闭前导出。',error:'无法生成和弦，请重试。',suggested:'推荐',all:'全部和弦',clear:'清除锁定',offset:'和弦偏移（毫秒；负值提前）',apply:'应用对齐'},
};
export default function BasicHarmony({data,jobId,language,value,onChange,onBeforeChange,onPlay,onPlayFrom,busy,currentMeasure}:{data:ScoreData;jobId:string;language:'en'|'zh';value:Harmony|null;onChange:(value:Harmony)=>void;onBeforeChange:()=>void;onPlay:(bar:number)=>void;onPlayFrom?:(bar:number)=>void;busy:boolean;currentMeasure?:number}){
  const text=words[language],key='melody-block-v1:'+data.scoreFingerprint;
  const [working,setWorking]=useState(false),[error,setError]=useState('');
  const [offsetText,setOffsetText]=useState(()=>{if(value)return String(value.alignment.offsetMs);try{const n=JSON.parse(localStorage.getItem(key)||'{}').chordOffsetMs;return String(typeof n==='number'&&Number.isFinite(n)?n:0);}catch{return '0';}});
  const offset=Number(offsetText),invalidOffset=!Number.isFinite(offset)||Math.abs(offset)>2000;
  const pending=useRef<AbortController|null>(null);
  useEffect(()=>()=>pending.current?.abort(),[]);
  const generate=async(locks?:Record<string,string>,phraseStarts?:number[],segmentLocks?:Record<string,string>)=>{
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    onBeforeChange();setWorking(true);setError('');
    try{
      let settings:{locks?:Record<string,string>;phraseStarts?:number[];segmentLocks?:Record<string,string>}={};
      if(!value&&locks===undefined){try{const stored=JSON.parse(localStorage.getItem(key)||'{}');if(stored&&typeof stored==='object'&&!Array.isArray(stored))settings=stored;}catch{settings={};}}
      const result=await api<Harmony>(`/api/jobs/${jobId}/harmony`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({scoreMode:data.scoreMode,melodyConfirmed:data.melodyConfirmed,harmonyPolicy:'adaptive-block-v1',bpm:data.bpm,meter:data.meter,key:data.key,sourceFingerprint:data.scoreFingerprint,editedNotes:data.editedNotes,identityNotesJson:data.identityNotesJson,anchorNoteId:data.downbeat?.noteId,downbeats:data.downbeats?.map(({noteId,measure})=>({noteId,measure})),chordOffsetMs:offset,locks:locks??value?.locks??settings.locks??{},segmentLocks:segmentLocks??value?.segmentLocks??settings.segmentLocks??{},phraseStarts:phraseStarts??value?.phraseStarts??settings.phraseStarts})});
      if(controller.signal.aborted)return;
      if(!result.alignment||result.sourceFingerprint!==data.scoreFingerprint)throw Error('Outdated score response');
      onChange(result);setOffsetText(String(result.alignment.offsetMs));
      try{localStorage.setItem(key,JSON.stringify({locks:result.locks,segmentLocks:result.segmentLocks,phraseStarts:result.phraseStarts,chordOffsetMs:result.alignment.offsetMs}));}catch{/* The active harmony is still retained in the project. */}
    }catch{if(!controller.signal.aborted)setError(text.error);}
    finally{if(!controller.signal.aborted)setWorking(false);}
  };
  const [measureFilter,setMeasureFilter]=useState('current');
  const [reviewOnly,setReviewOnly]=useState(false);
  const [lockedOnly,setLockedOnly]=useState(false);
  const exportChords=()=>{
    if(!value)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify({schemaVersion:1,kind:'basic-chords',sourceName:data.sourceName,sourceSha256:data.sourceSha256,bpm:data.bpm,meter:data.meter,key:data.key,baseFingerprint:data.baseFingerprint,downbeat:data.downbeat,grid:data.grid,...value},null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='basic-chords.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <section className="basic-harmony" aria-label={text.title}>
    <h3>{text.title}</h3>
    <div className="gf-review-row"><button className="primary-button" disabled={working||busy||!data.noteCount||invalidOffset} onClick={()=>void generate()}>{working?text.working:value?text.regenerate:text.generate}</button>{value&&<><button disabled={working||busy} onClick={()=>void generate({},undefined,{})}>{text.clear}</button><button disabled={working||busy} onClick={exportChords}>{text.export}</button></>}</div>
    <details><summary>{language==='zh'?'对齐设置':'Alignment settings'}</summary>    <div className="harmony-alignment"><label>{text.offset}<input aria-label={text.offset} type="number" min="-2000" max="2000" step="10" value={offsetText} disabled={working||busy} onChange={e=>setOffsetText(e.target.value)}/></label>{value&&offset!==value.alignment.offsetMs&&<button disabled={working||busy||invalidOffset} onClick={()=>void generate()}>{text.apply}</button>}</div>
</details>
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
    {value&&<><div className="harmony-filters">
      <select aria-label={language==='zh'?'和弦小节':'Harmony measure'} value={measureFilter} onChange={e=>setMeasureFilter(e.target.value)}>
        <option value="current">{language==='zh'?'当前小节':'Current measure'}</option>
        <option value="all">{language==='zh'?'全部小节':'All measures'}</option>
        {value.bars.map(bar=><option key={bar.number} value={bar.number}>{text.measure} {bar.displayNumber??bar.number}</option>)}
      </select>
      <label><input type="checkbox" checked={reviewOnly} onChange={event=>setReviewOnly(event.target.checked)}/>{text.review}</label>
      <label><input type="checkbox" checked={lockedOnly} onChange={event=>setLockedOnly(event.target.checked)}/>{text.lock}</label>
    </div><div className="harmony-cards">{(value.segments||value.bars).filter(bar=>(measureFilter==='all'||bar.number===(measureFilter==='current'?currentMeasure||1:Number(measureFilter)))&&(!reviewOnly||bar.needsReview)&&(!lockedOnly||bar.locked)).map(bar=><div key={'lockKey' in bar?String(bar.lockKey):bar.number} data-harmony-measure={bar.number} className={`harmony-card ${bar.locked?'chord-locked':''}`}>
      <div><button className="measure-table-link" disabled={working||busy} aria-label={`${language==='zh'?'从小节播放':'Play from measure'} ${bar.displayNumber??bar.number}`} onClick={()=>{if(onPlayFrom)onPlayFrom(bar.number);else onPlay(bar.number);}}>{bar.displayNumber??bar.number}{'beat' in bar?` · ${language==='zh'?'拍':'beat'} ${bar.beat}`:''} · {clock(bar.playStart??bar.start)}</button>{bar.needsReview&&<span className="harmony-review">{text.review}</span>}</div>
      <div><select aria-label={`${text.chord} ${bar.displayNumber??bar.number}${'beat' in bar?' · '+bar.beat:''}`} disabled={working||busy} value={bar.chordId} onChange={e=>'lockKey' in bar?void generate(value.locks,undefined,{...value.segmentLocks,[String(bar.lockKey)]:e.target.value}):void generate({...value.locks,[bar.number]:e.target.value})}><optgroup label={text.suggested}>{value.choices.filter(c=>bar.alternatives.includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name} · {c.roman}</option>)}</optgroup><optgroup label={text.all}>{value.choices.filter(c=>!bar.alternatives.includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name} · {c.roman}</option>)}</optgroup></select></div>
      <span>{bar.tones.join('–')||'—'}</span>
      <label><input type="checkbox" aria-label={`${text.phrase} ${bar.displayNumber??bar.number}`} disabled={working||busy||bar.number===1||('beat' in bar&&bar.beat!==1)} checked={bar.phraseStart} onChange={e=>void generate(value.locks,e.target.checked?[...value.phraseStarts,bar.number].sort((a,b)=>a-b):value.phraseStarts.filter(n=>n!==bar.number))} />{text.phrase}</label>
      <label><input type="checkbox" aria-label={`${text.lock} ${bar.displayNumber??bar.number}${'beat' in bar?' · '+bar.beat:''}`} checked={bar.locked} disabled={working||busy} onChange={e=>{if('lockKey' in bar){const locks={...value.segmentLocks};if(e.target.checked)locks[String(bar.lockKey)]=bar.chordId;else delete locks[String(bar.lockKey)];void generate(value.locks,undefined,locks);}else{const locks={...value.locks};if(e.target.checked)locks[bar.number]=bar.chordId;else delete locks[bar.number];void generate(locks);}}} />{text.lock}</label>
      <div><button disabled={working||busy} aria-label={`${text.hear} ${bar.displayNumber??bar.number}`} onClick={()=>onPlay(bar.number)}>{text.hear}</button></div>
    </div>)}</div><p role="status">{language==='zh'?'和弦已应用。下载工程文件以保留修改。':'Chords applied. Download the project to keep these changes.'}</p></>}
  </section>;
}
