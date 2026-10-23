import { useEffect, useRef, useState } from 'react';
import { api, clock } from './lib/api';
import type { BasicHarmony as Harmony, ScoreData } from './lib/api';

const words={
  en:{title:'Basic chords',generate:'Generate basic chords',regenerate:'Recalculate unlocked bars',working:'Preparing chords…',measure:'Measure / time',chord:'Chord',tones:'Chord tones',lock:'Lock',phrase:'New phrase',hear:'Hear measure',export:'Export chords',review:'Review',saved:'Chord settings saved.',unsaved:'Unable to save chord settings. Export before closing.',error:'Unable to generate chords. Please retry.',suggested:'Suggested',all:'All chords',clear:'Clear locks',offset:'Chord offset (ms; negative = earlier)',apply:'Apply timing'},
  zh:{title:'基本和弦',generate:'生成基本和弦',regenerate:'重新配置未锁定小节',working:'正在配置和弦…',measure:'小节 / 时间',chord:'和弦',tones:'组成音',lock:'锁定',phrase:'新乐句',hear:'试听小节',export:'导出和弦',review:'待核对',saved:'和弦设置已保存。',unsaved:'无法保存和弦设置，请在关闭前导出。',error:'无法生成和弦，请重试。',suggested:'推荐',all:'全部和弦',clear:'清除锁定',offset:'和弦偏移（毫秒；负值提前）',apply:'应用对齐'},
};
export default function BasicHarmony({data,jobId,language,value,onChange,onBeforeChange,onPlay,onPlayFrom,busy}:{data:ScoreData;jobId:string;language:'en'|'zh';value:Harmony|null;onChange:(value:Harmony)=>void;onBeforeChange:()=>void;onPlay:(bar:number)=>void;onPlayFrom?:(bar:number)=>void;busy:boolean}){
  const text=words[language],key='basic-harmony-v1:'+data.scoreFingerprint;
  const [working,setWorking]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(true);
  const [offsetText,setOffsetText]=useState(()=>{if(value)return String(value.alignment.offsetMs);try{const n=JSON.parse(localStorage.getItem(key)||'{}').chordOffsetMs;return String(typeof n==='number'&&Number.isFinite(n)?n:0);}catch{return '0';}});
  const offset=Number(offsetText),invalidOffset=!Number.isFinite(offset)||Math.abs(offset)>2000;
  const pending=useRef<AbortController|null>(null);
  useEffect(()=>()=>pending.current?.abort(),[]);
  const generate=async(locks?:Record<string,string>,phraseStarts?:number[])=>{
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    onBeforeChange();setWorking(true);setError('');
    try{
      let settings:{locks?:Record<string,string>;phraseStarts?:number[]}={};
      if(!value&&locks===undefined){try{const stored=JSON.parse(localStorage.getItem(key)||'{}');if(stored&&typeof stored==='object'&&!Array.isArray(stored))settings=stored;}catch{settings={};}}
      const result=await api<Harmony>(`/api/jobs/${jobId}/harmony`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bpm:data.bpm,meter:data.meter,key:data.key,sourceFingerprint:data.scoreFingerprint,anchorNoteId:data.downbeat?.noteId,chordOffsetMs:offset,locks:locks??value?.locks??settings.locks??{},phraseStarts:phraseStarts??value?.phraseStarts??settings.phraseStarts})});
      if(controller.signal.aborted)return;
      if(!result.alignment||result.sourceFingerprint!==data.scoreFingerprint)throw Error('Outdated score response');
      onChange(result);setOffsetText(String(result.alignment.offsetMs));
      try{localStorage.setItem(key,JSON.stringify({locks:result.locks,phraseStarts:result.phraseStarts,chordOffsetMs:result.alignment.offsetMs}));setSaved(true);}catch{setSaved(false);}
    }catch{if(!controller.signal.aborted)setError(text.error);}
    finally{if(!controller.signal.aborted)setWorking(false);}
  };
  const exportChords=()=>{
    if(!value)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify({schemaVersion:1,kind:'basic-chords',sourceName:data.sourceName,sourceSha256:data.sourceSha256,bpm:data.bpm,meter:data.meter,key:data.key,baseFingerprint:data.baseFingerprint,downbeat:data.downbeat,grid:data.grid,...value},null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='basic-chords.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <section className="basic-harmony" aria-label={text.title}>
    <h3>{text.title}</h3>
    <div className="harmony-alignment"><label>{text.offset}<input aria-label={text.offset} type="number" min="-2000" max="2000" step="10" value={offsetText} disabled={working||busy} onChange={e=>setOffsetText(e.target.value)}/></label>{value&&offset!==value.alignment.offsetMs&&<button disabled={working||busy||invalidOffset} onClick={()=>void generate()}>{text.apply}</button>}</div>
    <div className="gf-review-row"><button className="primary-button" disabled={working||busy||!data.noteCount||invalidOffset} onClick={()=>void generate()}>{working?text.working:value?text.regenerate:text.generate}</button>{value&&<><button disabled={working||busy} onClick={()=>void generate({})}>{text.clear}</button><button disabled={working||busy} onClick={exportChords}>{text.export}</button></>}</div>
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
    {value&&<><div className="harmony-table-scroll"><table><thead><tr><th>{text.measure}</th><th>{text.chord}</th><th>{text.tones}</th><th>{text.phrase}</th><th>{text.lock}</th><th /></tr></thead><tbody>{value.bars.map(bar=><tr key={bar.number} data-harmony-measure={bar.number} className={bar.locked?'chord-locked':''}>
      <td><button className="measure-table-link" disabled={working||busy} aria-label={`${language==='zh'?'从小节播放':'Play from measure'} ${bar.displayNumber??bar.number}`} onClick={()=>{if(onPlayFrom)onPlayFrom(bar.number);else onPlay(bar.number);}}>{bar.displayNumber??bar.number} · {clock(bar.playStart??bar.start)}</button>{bar.needsReview&&<span className="harmony-review">{text.review}</span>}</td>
      <td><select aria-label={`${text.chord} ${bar.displayNumber??bar.number}`} disabled={working||busy} value={bar.chordId} onChange={e=>void generate({...value.locks,[bar.number]:e.target.value})}><optgroup label={text.suggested}>{value.choices.filter(c=>bar.alternatives.includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name} · {c.roman}</option>)}</optgroup><optgroup label={text.all}>{value.choices.filter(c=>!bar.alternatives.includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name} · {c.roman}</option>)}</optgroup></select></td>
      <td>{bar.tones.join('–')||'—'}</td>
      <td><input type="checkbox" aria-label={`${text.phrase} ${bar.displayNumber??bar.number}`} disabled={working||busy||bar.number===1} checked={bar.phraseStart} onChange={e=>void generate(value.locks,e.target.checked?[...value.phraseStarts,bar.number].sort((a,b)=>a-b):value.phraseStarts.filter(n=>n!==bar.number))} /></td>
      <td><input type="checkbox" aria-label={`${text.lock} ${bar.displayNumber??bar.number}`} checked={bar.locked} disabled={working||busy} onChange={e=>{const locks={...value.locks};if(e.target.checked)locks[bar.number]=bar.chordId;else delete locks[bar.number];void generate(locks);}} /></td>
      <td><button disabled={working||busy} aria-label={`${text.hear} ${bar.displayNumber??bar.number}`} onClick={()=>onPlay(bar.number)}>{text.hear}</button></td>
    </tr>)}</tbody></table></div><p role="status">{saved?text.saved:text.unsaved}</p></>}
  </section>;
}
